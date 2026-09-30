import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import (
    get_intake_agent,
    get_intake_rate_limiter,
    get_ticket_rate_limiter,
    get_ticket_service,
)
from app.main import create_app
from app.models import ChatMessage, RoutingPrediction, SimilarIncident, TicketCreate
from app.services.incidents import parse_work_notes
from app.services.intake_chat import MAX_EMPLOYEE_MESSAGES, IntakeAgent, build_messages
from app.services.ratelimit import RateLimiter
from app.services.routing import to_prediction
from app.services.tickets import (
    ASSIGN_SQL,
    GET_SQL,
    INSERT_SQL,
    LIST_SQL,
    MAX_NUMBER_SQL,
    NOTE_SQL,
    RESOLVE_SQL,
    TicketService,
    is_live,
    journal_line,
)
from tests.fakes import FakeWarehouse
from tests.test_agent import ScriptedClient, final

NOW = datetime(2026, 9, 30, 9, 15, 0)


class Router:
    def __init__(self, group: str = "Network Operations", confidence: float = 0.93) -> None:
        self.group = group
        self.confidence = confidence

    def predict(self, text: str) -> RoutingPrediction:
        return to_prediction(
            [self.group, "Service Desk"], [self.confidence, 1 - self.confidence], "2"
        )

    def status(self) -> str:
        return "ready (v2)"


class Retriever:
    def __init__(self, score: float = 0.82) -> None:
        self.score = score

    def similar_incidents(self, text: str, k: int) -> list[SimilarIncident]:
        return [
            SimilarIncident(
                number="INC0015123", short_description="VPN drops", close_notes="Cleared cache.",
                category="network", subcategory="vpn", assignment_group="Network Operations",
                location="Remote", priority_label="3 - Moderate", mttr_hours=2.0,
                kb_reference="KB0010006", occurrences=12, score=self.score,
            )
        ]  # fmt: skip

    def kb_articles(self, text: str, k: int) -> list[Any]:
        return []


TICKET = TicketCreate(
    caller="Priya Shah",
    location="Remote",
    short_description="VPN drops after client update",
    description="Disconnects every few minutes since this morning's update.",
    impact=3,
    urgency=1,
    cmdb_ci="GlobalProtect VPN",
)


def make_service(
    warehouse: FakeWarehouse, router: Router | None = None, retriever: Retriever | None = None
) -> TicketService:
    return TicketService(warehouse, router or Router(), retriever or Retriever(), clock=lambda: NOW)


def test_confident_tickets_are_assigned_and_categorized() -> None:
    wh = FakeWarehouse({MAX_NUMBER_SQL: [{"n": None}]})

    created = make_service(wh).create(TICKET)

    assert created.number == "INC1000001"
    assert created.priority_label == "3 - Moderate"  # impact 3 x urgency 1
    assert created.assignment_group == "Network Operations"
    assert created.triage.mode == "auto"
    sql, params = wh.calls[-1]
    assert sql == INSERT_SQL
    assert params["subcategory"] == "vpn"
    assert params["now"] == "2026-09-30 09:15:00"
    notes = parse_work_notes(params["work_notes"])
    assert [n.author for n in notes] == ["Virtual Agent", "Routing model", "Routing model"]
    assert "Assigned to Network Operations (93% confidence)" in notes[1].text
    assert "closest precedent, INC0015123" in notes[2].text


def test_uncertain_tickets_wait_for_review_and_weak_matches_stay_uncategorized() -> None:
    wh = FakeWarehouse({MAX_NUMBER_SQL: [{"n": 1000007}]})

    created = make_service(wh, Router("Service Desk", 0.55), Retriever(0.4)).create(TICKET)

    assert created.number == "INC1000008"  # continues after the highest number stored
    assert created.assignment_group is None
    assert created.triage.mode == "review"
    params = wh.calls[-1][1]
    assert params["assignment_group"] == "" and params["subcategory"] == ""
    assert "Waiting for dispatcher review" in params["work_notes"]


def test_numbers_are_allocated_once_per_process() -> None:
    wh = FakeWarehouse({MAX_NUMBER_SQL: [{"n": None}]})
    svc = make_service(wh)

    numbers = [svc.create(TICKET).number for _ in range(3)]

    assert numbers == ["INC1000001", "INC1000002", "INC1000003"]
    assert sum(sql == MAX_NUMBER_SQL for sql, _ in wh.calls) == 1


def open_ticket(group: str | None = None, resolved: bool = False) -> dict[str, Any]:
    return {
        "number": "INC1000001",
        "state": "New",
        "assignment_group": group,
        "triage_mode": "review",
        "is_resolved": resolved,
    }


def test_assigning_a_reviewed_ticket_and_reassigning_it() -> None:
    wh = FakeWarehouse({GET_SQL: [open_ticket()]})
    svc = make_service(wh)

    svc.assign("inc1000001", "Network Operations")
    wh.responses[GET_SQL] = [open_ticket("Network Operations")]
    svc.assign("INC1000001", "Warehouse Systems")
    svc.assign("INC1000001", "Network Operations")  # no change: nothing written

    updates = [p for sql, p in wh.calls if sql == ASSIGN_SQL]
    assert len(updates) == 2
    assert updates[0]["line"].endswith(
        "Reviewed the routing suggestion. Assigned to Network Operations."
    )
    # Reassignments use the history's wording, so reassignment counts and timelines work.
    assert updates[1]["line"].endswith(
        "Not a Network Operations issue. Reassigning to Warehouse Systems."
    )
    assert parse_work_notes(updates[1]["line"])[0].kind == "reassignment"


def test_notes_and_resolution() -> None:
    wh = FakeWarehouse({GET_SQL: [open_ticket("Network Operations")]})
    svc = make_service(wh)
    from app.models import TicketResolve

    svc.add_note("INC1000001", "Called the user.\nCleared the portal cache.")
    svc.resolve(
        "INC1000001",
        TicketResolve(close_code="Solved Remotely (Permanently)", close_notes="Cleared cache."),
    )

    note = next(p for sql, p in wh.calls if sql == NOTE_SQL)
    assert (
        note["line"]
        == "2026-09-30 09:15:00 - Dispatcher: Called the user. Cleared the portal cache."
    )
    resolved = next(p for sql, p in wh.calls if sql == RESOLVE_SQL)
    assert resolved["close_code"] == "Solved Remotely (Permanently)"


def test_journal_lines_parse_like_history() -> None:
    line = journal_line(NOW, "Dispatcher", "Multi\nline   text")

    assert parse_work_notes(line)[0].text == "Multi line text"


@pytest.mark.parametrize(
    ("number", "live"),
    [("INC1000001", True), ("inc1000123", True), ("INC0017396", False), ("INCabcdefg", False)],
)
def test_live_numbers_are_a_separate_range(number: str, live: bool) -> None:
    assert is_live(number) is live


# --- HTTP ---


@pytest.fixture
def warehouse() -> FakeWarehouse:
    return FakeWarehouse(
        {
            MAX_NUMBER_SQL: [{"n": None}],
            GET_SQL: [open_ticket()],
            LIST_SQL: [
                {
                    "number": "INC1000001",
                    "opened_at": "2026-09-30 09:15:00",
                    "state": "New",
                    "caller": "Priya Shah",
                    "location": "Remote",
                    "priority_label": "3 - Moderate",
                    "short_description": "VPN drops",
                    "assignment_group": None,
                    "suggested_group": "Network Operations",
                    "triage_confidence": 0.55,
                    "triage_mode": "review",
                }
            ],
        }
    )


TURN = {
    "reply": "Thanks. Does anyone else at your site have the same problem?",
    "ready": False,
    "ticket": {
        "short_description": "VPN drops after client update",
        "description": "Employee reports VPN disconnects.",
        "impact": 3,
        "urgency": 2,
        "cmdb_ci": "",
    },
}


@pytest.fixture
def claude() -> ScriptedClient:
    return ScriptedClient(final(json.dumps(TURN)))


@pytest.fixture
def client(warehouse: FakeWarehouse, claude: ScriptedClient) -> Iterator[TestClient]:
    app = create_app()
    svc = make_service(warehouse)
    writes, chats = RateLimiter(30, 600, 1000), RateLimiter(20, 600, 400)
    app.dependency_overrides[get_ticket_service] = lambda: svc
    app.dependency_overrides[get_ticket_rate_limiter] = lambda: writes
    app.dependency_overrides[get_intake_agent] = lambda: IntakeAgent(claude, "claude-opus-5-5")
    app.dependency_overrides[get_intake_rate_limiter] = lambda: chats
    yield TestClient(app)


def test_ticket_endpoints(client: TestClient, warehouse: FakeWarehouse) -> None:
    created = client.post("/api/tickets", json=TICKET.model_dump())
    assert created.status_code == 201
    assert created.json()["triage"]["mode"] == "auto"

    queue = client.get("/api/tickets?view=review").json()
    assert queue[0]["suggested_group"] == "Network Operations"
    assert dict(warehouse.calls)[LIST_SQL] == {"review_only": 1}

    assert (
        client.post(
            "/api/tickets/INC1000001/assign", json={"group": "Network Operations"}
        ).status_code
        == 200
    )
    assert client.post("/api/tickets/INC1000001/notes", json={"text": "On it."}).status_code == 200


def test_ticket_endpoint_errors(client: TestClient, warehouse: FakeWarehouse) -> None:
    assert client.post("/api/tickets/INC0017396/notes", json={"text": "x"}).status_code == 404
    assert (
        client.post("/api/tickets/INC1000001/assign", json={"group": "Nobody"}).status_code == 422
    )
    assert client.post("/api/tickets", json=TICKET.model_dump() | {"impact": 4}).status_code == 422
    assert (
        client.post("/api/tickets", json=TICKET.model_dump() | {"location": "Mars"}).status_code
        == 422
    )
    warehouse.responses[GET_SQL] = [open_ticket("Network Operations", resolved=True)]
    resolve = {"close_code": "Solved (Permanently)", "close_notes": "Fixed it."}
    assert client.post("/api/tickets/INC1000001/resolve", json=resolve).status_code == 409


def test_chat_turn(client: TestClient, claude: ScriptedClient) -> None:
    response = client.post(
        "/api/intake/chat",
        json={
            "caller": "Priya Shah",
            "location": "Remote",
            "messages": [{"role": "user", "content": "My VPN keeps dropping"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["turn"]["ready"] is False
    sent = claude.calls[0]["messages"]
    assert sent[0]["content"].startswith("[Employee: Priya Shah, site: Remote]\nMy VPN")


def test_chat_must_end_with_the_employee(client: TestClient) -> None:
    body = {
        "caller": "Priya Shah",
        "location": "Remote",
        "messages": [
            {"role": "user", "content": "VPN"},
            {"role": "assistant", "content": "Tell me more"},
        ],
    }
    assert client.post("/api/intake/chat", json=body).status_code == 422


def test_question_budget_is_enforced(claude: ScriptedClient) -> None:
    transcript = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
        for i in range(2 * MAX_EMPLOYEE_MESSAGES - 1)
    ]

    messages = build_messages("Priya Shah", "Remote", transcript)
    result = IntakeAgent(claude, "m").turn("Priya Shah", "Remote", transcript)

    assert "[No more questions" in messages[-1]["content"]
    assert result.value.ready is True  # forced even though the model said not ready
