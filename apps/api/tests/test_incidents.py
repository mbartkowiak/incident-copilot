import json
from collections.abc import Iterator
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import (
    get_incident_service,
    get_summarizer,
    get_summary_cache,
    get_summary_rate_limiter,
)
from app.main import create_app
from app.services.cache import TTLCache
from app.services.incidents import (
    AS_OF_SQL,
    DETAIL_SQL,
    LIST_SQL,
    RISK_SQL,
    IncidentService,
    breach_risk,
    parse_work_notes,
)
from app.services.ratelimit import RateLimiter
from app.services.summary import TicketSummarizer, ticket_prompt
from tests.fakes import FakeWarehouse
from tests.test_agent import ScriptedClient, final

NOTES = (
    "2026-08-18 12:50:22 - Uma Edwards: Acknowledged. Reviewing the ticket details.\n"
    "2026-08-18 18:31:01 - Deepa Flores: Not a Network Operations issue. "
    "Reassigning to Warehouse Systems.\n"
    "2026-08-18 20:58:45 - Malik Kaur: Working KB0010028: Check the device in MDM.\n"
    "2026-08-18 21:10:00 - Malik Kaur: Waiting on vendor response. Placing On Hold.\n"
    "2026-08-19 07:23:34 - Malik Kaur: Resolved. See close notes."
)

DETAIL = {
    "number": "INC0017396",
    "state": "Closed",
    "opened_at": "2026-08-18 12:04:45",
    "resolved_at": "2026-08-19 07:23:34",
    "closed_at": "2026-08-26 07:23:34",
    "priority": 2,
    "priority_label": "2 - High",
    "short_description": "Scanner won't connect to WMS",
    "description": "Handheld keeps dropping off Wi-Fi.",
    "category": "hardware",
    "subcategory": "handheld",
    "cmdb_ci": "HH-MEM-032",
    "location": "Memphis DC",
    "contact_type": "phone",
    "assignment_group": "Warehouse Systems",
    "assigned_to": "Malik Kaur",
    "reassignment_count": 1,
    "reopen_count": 0,
    "close_code": "Solved (Permanently)",
    "close_notes": "Re-enrolled device in MDM.",
    "work_notes": NOTES,
    "sla_target_hours": 8,
    "sla_breached": True,
    "mttr_hours": 19.31,
    "is_resolved": True,
}

OPEN = DETAIL | {
    "number": "INC0018320",
    "state": "On Hold",
    "opened_at": "2026-09-27 12:00:00",
    "resolved_at": None,
    "closed_at": None,
    "sla_breached": False,
    "mttr_hours": None,
    "close_code": None,
    "close_notes": None,
    "work_notes": None,
}

RISK = {
    "similar_tickets": 45,
    "similar_breaches": 13,
    "priority_rate": 0.27,
    "misrouted_rate": 0.7,
    "routed_right_rate": 0.11,
}

ROW = {
    "number": "INC0018320",
    "opened_at": "2026-09-27 12:00:00",
    "state": "On Hold",
    "priority_label": "2 - High",
    "short_description": "Scanner won't connect",
    "assignment_group": "Warehouse Systems",
    "subcategory": "handheld",
    "location": "Memphis DC",
    "is_resolved": False,
    "sla_breached": False,
    "mttr_hours": None,
}


class NumberedWarehouse(FakeWarehouse):
    """Answers DETAIL_SQL by the bound ticket number."""

    def __init__(self, tickets: dict[str, dict[str, Any]]) -> None:
        super().__init__({AS_OF_SQL: [{"as_of": "2026-09-27"}], RISK_SQL: [RISK], LIST_SQL: [ROW]})
        self.tickets = tickets

    def query(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        rows = super().query(sql, params)
        if sql == DETAIL_SQL:
            ticket = self.tickets.get(params["number"])
            return [ticket] if ticket else []
        return rows


SUMMARY = {
    "headline": "Memphis scanner can't reach WMS.",
    "status": "Closed by Warehouse Systems; SLA breached.",
    "actions_taken": ["Reassigned from Network Operations", "Re-enrolled device in MDM"],
    "next_step": "None",
    "watch_outs": ["Misrouted first"],
}


@pytest.fixture
def warehouse() -> NumberedWarehouse:
    return NumberedWarehouse({"INC0017396": DETAIL, "INC0018320": OPEN})


@pytest.fixture
def service(warehouse: NumberedWarehouse) -> IncidentService:
    return IncidentService(warehouse, TTLCache(60))


@pytest.fixture
def claude() -> ScriptedClient:
    return ScriptedClient(final(json.dumps(SUMMARY)))


@pytest.fixture
def client(service: IncidentService, claude: ScriptedClient) -> Iterator[TestClient]:
    app = create_app()
    limiter = RateLimiter(per_client=2, per_client_window_s=600, daily=100)
    cache = TTLCache(60)
    app.dependency_overrides[get_incident_service] = lambda: service
    app.dependency_overrides[get_summarizer] = lambda: TicketSummarizer(claude, "claude-opus-5-5")
    app.dependency_overrides[get_summary_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_summary_cache] = lambda: cache
    yield TestClient(app)


def test_work_notes_parse_into_typed_entries() -> None:
    notes = parse_work_notes(NOTES + "\ncontinued on a second line")

    assert [n.kind for n in notes] == ["note", "reassignment", "note", "hold", "resolution"]
    assert notes[1].author == "Deepa Flores"
    assert notes[0].at == datetime(2026, 8, 18, 12, 50, 22)
    assert notes[-1].text.endswith("\ncontinued on a second line")
    assert parse_work_notes(None) == []


def test_detail_derives_first_team_sla_and_risk(service: IncidentService) -> None:
    ticket = service.get("inc0017396")

    assert ticket.initial_group == "Network Operations"
    assert ticket.sla.due_at == datetime(2026, 8, 18, 20, 4, 45)
    assert ticket.sla.elapsed_hours == 19.31
    assert ticket.sla.breached
    assert ticket.risk.misrouted_rate == 0.7
    assert ticket.as_of == date(2026, 9, 27)


def test_open_ticket_clock_runs_to_the_end_of_the_extract(service: IncidentService) -> None:
    ticket = service.get("INC0018320")

    assert ticket.resolved_at is None
    assert ticket.initial_group == "Warehouse Systems"  # never reassigned
    assert ticket.sla.elapsed_hours == pytest.approx(12.0, abs=0.01)  # noon to 23:59:59


def test_breach_risk_is_smoothed_toward_the_priority_rate() -> None:
    risk = breach_risk(RISK | {"similar_tickets": 1, "similar_breaches": 1})

    assert risk.similar_rate == pytest.approx((1 + 5 * 0.27) / 6, abs=1e-4)
    assert breach_risk({}).similar_rate == 0.0  # no history at all


def test_list_binds_every_filter(service: IncidentService, warehouse: NumberedWarehouse) -> None:
    result = service.list("resolved", 2, "Warehouse Systems", True, " scanner ", 25)

    assert result.incidents[0].number == "INC0018320"
    sql, params = warehouse.calls[0]
    assert sql == LIST_SQL
    assert params == {
        "status": "resolved",
        "priority": 2,
        "assignment_group": "Warehouse Systems",
        "breached_only": 1,
        "q": "scanner",
        "limit": 25,
    }


def test_incident_endpoints(client: TestClient) -> None:
    listing = client.get("/api/incidents?status=all&group=Warehouse%20Systems&breached=true")
    assert listing.status_code == 200
    assert listing.json()["as_of"] == "2026-09-27"

    detail = client.get("/api/incidents/INC0017396").json()
    assert detail["work_notes"][1]["kind"] == "reassignment"
    assert detail["opened_at"] == "2026-08-18T12:04:45"  # naive wall-clock time

    assert client.get("/api/incidents/INC0000001").status_code == 404
    assert client.get("/api/incidents/DROP%20TABLE").status_code == 422
    assert client.get("/api/incidents?group=Not%20A%20Team").status_code == 422


def test_summary_is_generated_once_then_served_from_cache(
    client: TestClient, claude: ScriptedClient
) -> None:
    first = client.post("/api/incidents/INC0017396/summary")
    second = client.post("/api/incidents/inc0017396/summary")

    assert first.status_code == 200
    assert first.json()["summary"]["headline"] == SUMMARY["headline"]
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert len(claude.calls) == 1

    call = claude.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["effort"] == "low"
    assert call["fallbacks"] == "default"
    prompt = call["messages"][0]["content"]
    assert "First assigned to: Network Operations" in prompt
    assert "BREACHED" in prompt


def test_only_fresh_summaries_count_against_the_rate_limit(client: TestClient) -> None:
    for _ in range(3):  # one fresh call plus cache hits; the limit is two per client
        assert client.post("/api/incidents/INC0017396/summary").status_code == 200
    assert client.post("/api/incidents/INC0018320/summary").status_code == 200

    response = client.post("/api/incidents/INC0018320/summary")
    assert response.status_code == 200  # cached
    assert response.json()["cached"] is True


def test_rate_limit_applies_to_new_tickets(
    service: IncidentService, warehouse: NumberedWarehouse, claude: ScriptedClient
) -> None:
    warehouse.tickets["INC0000003"] = OPEN | {"number": "INC0000003"}
    limiter, cache = RateLimiter(1, 600, 100, what="AI summaries"), TTLCache(60)
    app = create_app()
    app.dependency_overrides[get_incident_service] = lambda: service
    app.dependency_overrides[get_summarizer] = lambda: TicketSummarizer(claude, "claude-opus-5-5")
    app.dependency_overrides[get_summary_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_summary_cache] = lambda: cache
    client = TestClient(app)

    assert client.post("/api/incidents/INC0017396/summary").status_code == 200
    limited = client.post("/api/incidents/INC0000003/summary")
    assert limited.status_code == 429
    assert "AI summaries" in limited.json()["detail"]


def test_refused_summary_returns_502_and_is_not_cached(
    service: IncidentService,
) -> None:
    refusing = ScriptedClient(final("", stop_reason="refusal"))
    limiter, cache = RateLimiter(5, 600, 100), TTLCache(60)
    app = create_app()
    app.dependency_overrides[get_incident_service] = lambda: service
    app.dependency_overrides[get_summarizer] = lambda: TicketSummarizer(refusing, "claude-opus-5-5")
    app.dependency_overrides[get_summary_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_summary_cache] = lambda: cache
    client = TestClient(app)

    assert client.post("/api/incidents/INC0017396/summary").status_code == 502
    assert client.post("/api/incidents/INC0017396/summary").status_code == 502
    assert len(refusing.calls) == 2


def test_prompt_marks_open_tickets_without_notes(service: IncidentService) -> None:
    prompt = ticket_prompt(service.get("INC0018320"))

    assert "not yet breached" in prompt
    assert "- (none yet)" in prompt
    assert "Close notes" not in prompt


def test_summary_usage_is_costed() -> None:
    claude = ScriptedClient(
        SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(SUMMARY))],
            usage=SimpleNamespace(
                input_tokens=1_000_000,
                output_tokens=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )
    )
    service = IncidentService(NumberedWarehouse({"INC0017396": DETAIL}), TTLCache(60))

    result = TicketSummarizer(claude, "claude-opus-5-5").summarize(service.get("INC0017396"))

    assert result.cost_usd == 4.0
