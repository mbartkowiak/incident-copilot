from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_servicenow_connector
from app.main import create_app
from app.models import TicketCreated, TicketFields, TicketResolve, TriageOutcome
from app.services.servicenow import CLOSE_CODE_CANDIDATES, ServiceNowClient, ServiceNowError
from app.services.sync import ServiceNowConnector

INSTANCE = "https://dev000000.service-now.com"


def ref(value: str, display: str = "") -> dict[str, str]:
    return {"value": value, "display_value": display or value}


class FakeServiceNow:
    instance = INSTANCE

    def __init__(self) -> None:
        self.records = {
            ("sys_user", "Priya Shah"): "user-priya",
            ("cmn_location", "Remote"): "loc-remote",
            ("sys_user_group", "Network Operations"): "grp-netops",
        }
        self.created: list[dict[str, Any]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.queries: dict[str, list[dict[str, Any]]] = {}
        self.fail = False

    def find(self, table: str, name: str, field: str = "name") -> str | None:
        return self.records.get((table, name))

    def create_incident(self, fields: dict[str, Any]) -> dict[str, str]:
        if self.fail:
            raise ServiceNowError("POST table/incident: HTTP 503")
        self.created.append(fields)
        return {"sys_id": f"sn-{len(self.created)}", "number": f"INC00100{len(self.created):02d}"}

    def update_incident(self, sys_id: str, fields: dict[str, Any]) -> None:
        if self.fail:
            raise ServiceNowError("PATCH: HTTP 503")
        self.updates.append((sys_id, fields))

    def incidents(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        if self.fail:
            raise ServiceNowError("GET table/incident: HTTP 503")
        for prefix, rows in self.queries.items():
            if query.startswith(prefix):
                return rows
        return []

    def close_code(self, app_code: str) -> str:
        return "Solution provided"


TRIAGE = TriageOutcome(
    suggested_group="Network Operations",
    confidence=0.93,
    mode="auto",
    category="network",
    subcategory="vpn",
    precedent="INC0015123",
)


class FakeTickets:
    """The slice of TicketService the connector uses, in memory."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.links: list[tuple[str, str, str]] = []
        self.external: list[dict[str, Any]] = []
        self.pending: list[dict[str, Any]] = []
        self.queries = 0  # warehouse round trips; each one wakes the SQL warehouse

    def link(self, number: str, sn_sys_id: str, sn_number: str) -> None:
        self.links.append((number, sn_sys_id, sn_number))

    def unlinked(self) -> list[dict[str, Any]]:
        self.queries += 1
        return self.pending

    def by_servicenow_id(self, sn_sys_id: str) -> dict[str, Any] | None:
        self.queries += 1
        return next((r for r in self.rows.values() if r["sn_sys_id"] == sn_sys_id), None)

    def create(
        self, ticket: TicketFields, origin: str, sn_sys_id: str, sn_number: str
    ) -> TicketCreated:
        number = f"INC100000{len(self.rows) + 1}"
        self.rows[number] = {
            "number": number, "state": "New", "assignment_group": None, "is_resolved": False,
            "sn_sys_id": sn_sys_id, "origin": origin, "close_code": None, "close_notes": None,
            "caller": ticket.caller, "location": ticket.location,
        }  # fmt: skip
        return TicketCreated(
            number=number, priority_label="3 - Moderate", state="New",
            assignment_group="Network Operations", triage=TRIAGE,
        )  # fmt: skip

    def apply_external(self, number: str, **change: Any) -> None:
        self.external.append({"number": number, **change})
        self.rows[number]["state"] = change["state"]


@pytest.fixture
def sn() -> FakeServiceNow:
    return FakeServiceNow()


@pytest.fixture
def tickets() -> FakeTickets:
    return FakeTickets()


@pytest.fixture
def connector(sn: FakeServiceNow, tickets: FakeTickets) -> ServiceNowConnector:
    c = ServiceNowConnector(sn)
    c.tickets = tickets  # type: ignore[assignment]
    return c


TICKET = TicketFields(
    caller="Priya Shah",
    location="Remote",
    contact_type="virtual_agent",
    short_description="VPN fails with PORTAL_CFG_READ",
    description="Can't connect since the update.",
    impact=3,
    urgency=1,
)


def test_app_tickets_are_created_in_servicenow_and_linked(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    number = connector.created("INC1000001", TICKET, TRIAGE, 3)

    fields = sn.created[0]
    assert number == "INC0010001"
    assert fields["correlation_id"] == "INC1000001"
    assert fields["caller_id"] == "user-priya"
    assert fields["location"] == "loc-remote"
    assert fields["assignment_group"] == "grp-netops"
    assert (fields["impact"], fields["urgency"]) == ("3", "1")
    assert "Assigned to Network Operations (93% confidence)" in fields["work_notes"]
    assert tickets.links == [("INC1000001", "sn-1", "INC0010001")]


def test_unknown_callers_are_named_in_the_description_and_review_tickets_stay_unassigned(
    connector: ServiceNowConnector, sn: FakeServiceNow
) -> None:
    review = TRIAGE.model_copy(update={"mode": "review", "confidence": 0.3})
    connector.created("INC1000002", TICKET.model_copy(update={"caller": "New Hire"}), review, 3)

    fields = sn.created[0]
    assert "caller_id" not in fields
    assert fields["description"].startswith("Caller: New Hire, Remote")
    assert "assignment_group" not in fields


def test_a_servicenow_outage_never_blocks_the_app(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    sn.fail = True

    assert connector.created("INC1000001", TICKET, TRIAGE, 3) is None
    connector.noted(
        {"number": "INC1000001", "sn_sys_id": "sn-1", "state": "New"}, "Dispatcher: on it"
    )
    connector.sync_once()

    assert tickets.links == []
    status = connector.status()
    assert status.last_error is not None and "503" in status.last_error


def test_changes_are_mirrored_to_linked_incidents_only(
    connector: ServiceNowConnector, sn: FakeServiceNow
) -> None:
    linked = {"number": "INC1000001", "sn_sys_id": "sn-1", "state": "New"}

    connector.assigned(linked, "Network Operations", "Dispatcher: Assigned to Network Operations.")
    connector.noted(linked, "Dispatcher: Cleared the portal cache.")
    connector.resolved(
        linked,
        TicketResolve(close_code="Solved Remotely (Permanently)", close_notes="Cache cleared."),
        "Dispatcher: Resolved.",
    )
    connector.noted({"number": "INC1000009", "sn_sys_id": None, "state": "New"}, "x")

    assert [u[1].get("state") for u in sn.updates] == [None, "2", "6"]
    assert sn.updates[0][1]["assignment_group"] == "grp-netops"
    assert sn.updates[2][1]["close_code"] == "Solution provided"
    assert len(sn.updates) == 3  # the unlinked ticket wasn't sent


def servicenow_incident(**overrides: Any) -> dict[str, Any]:
    return {
        "sys_id": ref("abc123"),
        "number": ref("INC0010042"),
        "state": ref("1", "New"),
        "short_description": ref("Printer at dock 3 prints blank labels"),
        "description": ref("Raised by phone."),
        "caller_id": ref("user-ana", "Ana Torres"),
        "location": ref("loc-dallas", "Dallas DC"),
        "contact_type": ref("phone", "Phone"),
        "impact": ref("2", "2 - Medium"),
        "urgency": ref("2", "2 - Medium"),
        "assignment_group": ref("", ""),
        "category": ref("inquiry", "Inquiry / Help"),
        "close_code": ref(""),
        "close_notes": ref(""),
        **overrides,
    }


def test_incidents_raised_in_servicenow_are_imported_triaged_and_annotated(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    sn.queries["active=true^correlation_idISEMPTY"] = [servicenow_incident()]

    connector.sync_once()
    connector.sync_once()  # already imported: not imported twice

    assert len(tickets.rows) == 1
    local = tickets.rows["INC1000001"]
    assert (local["origin"], local["caller"], local["location"]) == (
        "servicenow",
        "Ana Torres",
        "Dallas DC",
    )
    sys_id, fields = sn.updates[0]
    assert sys_id == "abc123"
    assert fields["correlation_id"] == "INC1000001"
    assert fields["assignment_group"] == "grp-netops"  # confident, and nobody had assigned it
    assert "Closest precedent: INC0015123" in fields["work_notes"]
    assert fields["category"] == "network"  # the form default is replaced
    assert connector.status().imported == 1


def test_a_human_assignment_in_servicenow_is_never_overridden(
    connector: ServiceNowConnector, sn: FakeServiceNow
) -> None:
    sn.queries["active=true^correlation_idISEMPTY"] = [
        servicenow_incident(
            assignment_group=ref("grp-eud", "End User Computing"),
            category=ref("software", "Software"),
        )
    ]

    connector.sync_once()

    assert "assignment_group" not in sn.updates[0][1]
    assert "category" not in sn.updates[0][1]


def test_changes_made_in_servicenow_flow_back_and_echoes_are_ignored(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    tickets.rows["INC1000001"] = {
        "number": "INC1000001", "state": "In Progress", "assignment_group": "Network Operations",
        "is_resolved": False, "sn_sys_id": "abc123", "close_code": None, "close_notes": None,
    }  # fmt: skip
    resolved = servicenow_incident(
        state=ref("6", "Resolved"),
        assignment_group=ref("grp-netops", "Network Operations"),
        close_code=ref("Solution provided"),
        close_notes=ref("Re-imaged the laptop."),
    )
    sn.queries["correlation_idSTARTSWITHINC1"] = [resolved]

    connector.sync_once()
    connector.sync_once()  # same values again: nothing new to apply

    assert len(tickets.external) == 1
    change = tickets.external[0]
    assert change["state"] == "Resolved"
    assert change["close_notes"] == "Re-imaged the laptop."
    assert change["text"] == "Updated in INC0010042: state is now Resolved."


def test_unlinked_app_tickets_are_pushed_on_the_next_sync(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    tickets.pending = [
        {
            "number": "INC1000003", "caller": "Priya Shah", "location": "Remote",
            "contact_type": "virtual_agent", "short_description": "VPN down", "description": "",
            "impact": 3, "urgency": 1, "suggested_group": "Service Desk",
            "triage_confidence": 0.3, "triage_mode": "manual", "category": "network",
            "subcategory": "vpn", "assignment_group": "Network Operations", "state": "In Progress",
        }
    ]  # fmt: skip

    connector.sync_once()

    pushed = sn.created[0]
    assert pushed["correlation_id"] == "INC1000003"
    # The dispatcher's assignment and progress, not the creation-time triage, reach ServiceNow.
    assert pushed["assignment_group"] == "grp-netops"
    assert pushed["state"] == "2"
    assert tickets.links[0][0] == "INC1000003"


def test_quiet_passes_leave_the_warehouse_asleep(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    connector.sync_once()  # catch-up after a restart: one look for unlinked tickets
    assert tickets.queries == 1

    for _ in range(5):
        connector.sync_once()

    assert tickets.queries == 1


def test_a_failed_push_is_retried_on_the_next_pass(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    connector.sync_once()
    sn.fail = True
    connector.created("INC1000003", TICKET, TRIAGE, 3)
    sn.fail = False
    tickets.pending = [
        {
            "number": "INC1000003", "caller": "Priya Shah", "location": "Remote",
            "contact_type": "virtual_agent", "short_description": "VPN down", "description": "",
            "impact": 3, "urgency": 1, "suggested_group": "Network Operations",
            "triage_confidence": 0.93, "triage_mode": "auto", "category": "network",
            "subcategory": "vpn", "assignment_group": "Network Operations", "state": "New",
        }
    ]  # fmt: skip

    connector.sync_once()
    tickets.pending = []
    connector.sync_once()

    assert [c["correlation_id"] for c in sn.created] == ["INC1000003"]
    assert tickets.queries == 2  # the startup catch-up and the retry


def test_an_unchanged_incident_is_looked_up_once_while_in_the_update_window(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    tickets.rows["INC1000001"] = {
        "number": "INC1000001", "state": "New", "assignment_group": "Network Operations",
        "is_resolved": False, "sn_sys_id": "abc123", "close_code": None, "close_notes": None,
    }  # fmt: skip
    updated = servicenow_incident(
        state=ref("2", "In Progress"),
        assignment_group=ref("grp-netops", "Network Operations"),
        sys_updated_on=ref("2026-10-03 09:00:00"),
    )
    sn.queries["correlation_idSTARTSWITHINC1"] = [updated]
    connector.sync_once()
    queries = tickets.queries

    connector.sync_once()
    connector.sync_once()
    assert tickets.queries == queries

    sn.queries["correlation_idSTARTSWITHINC1"] = [
        {**updated, "state": ref("6", "Resolved"), "sys_updated_on": ref("2026-10-03 09:05:00")}
    ]
    connector.sync_once()

    assert tickets.queries == queries + 1
    assert [c["state"] for c in tickets.external] == ["In Progress", "Resolved"]


def test_close_codes_map_to_the_labels_the_instance_offers(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ServiceNowClient(INSTANCE, "u", "p")
    monkeypatch.setattr(
        client,
        "_call",
        lambda *a, **k: [{"value": "Solution provided"}, {"value": "Workaround provided"}],
    )

    assert client.close_code("Solved (Permanently)") == "Solution provided"
    assert client.close_code("Solved Remotely (Work Around)") == "Workaround provided"
    assert set(CLOSE_CODE_CANDIDATES) >= {"Closed/Resolved by Caller"}


def test_close_codes_are_learned_from_resolved_incidents_without_the_choice_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ServiceNowClient(INSTANCE, "u", "p")

    def call(method: str, path: str, **kwargs: Any) -> Any:
        if path == "table/sys_choice":  # itil can't read it
            raise ServiceNowError("GET table/sys_choice: HTTP 403")
        return [
            {"close_code": "Solution provided"},
            {"close_code": "Workaround provided"},
            {"close_code": "Solution provided"},
        ]

    monkeypatch.setattr(client, "_call", call)

    assert client.close_code("Solved Remotely (Permanently)") == "Solution provided"
    assert client.close_code("Solved (Work Around)") == "Workaround provided"


def test_status_endpoint_when_not_configured() -> None:
    app = create_app()
    app.dependency_overrides[get_servicenow_connector] = lambda: None
    client = TestClient(app)

    assert client.get("/api/servicenow/status").json()["enabled"] is False
    assert client.post("/api/servicenow/sync").status_code == 503


def test_status_endpoint_reports_the_connector(connector: ServiceNowConnector) -> None:
    app = create_app()
    app.dependency_overrides[get_servicenow_connector] = lambda: connector

    body = TestClient(app).get("/api/servicenow/status").json()

    assert body["enabled"] is True
    assert body["instance"] == INSTANCE


SECRET_SYS_ID = "a" * 32


def test_events_import_one_incident_and_ignore_linked_ones(
    connector: ServiceNowConnector, sn: FakeServiceNow, tickets: FakeTickets
) -> None:
    sn.queries[f"sys_id={SECRET_SYS_ID}"] = [servicenow_incident(sys_id=ref(SECRET_SYS_ID))]

    assert connector.import_one(SECRET_SYS_ID) == "INC1000001"
    assert connector.import_one(SECRET_SYS_ID) is None  # already linked
    assert connector.import_one("b" * 32) is None  # unknown or inactive
    assert len(tickets.rows) == 1


def test_event_endpoint_requires_the_shared_secret(
    connector: ServiceNowConnector, sn: FakeServiceNow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings
    from app.deps import get_ticket_rate_limiter
    from app.services.ratelimit import RateLimiter

    sn.queries[f"sys_id={SECRET_SYS_ID}"] = [servicenow_incident(sys_id=ref(SECRET_SYS_ID))]
    app = create_app()
    app.dependency_overrides[get_servicenow_connector] = lambda: connector
    app.dependency_overrides[get_ticket_rate_limiter] = lambda: RateLimiter(10, 600, 100)
    client = TestClient(app)
    body = {"sys_id": SECRET_SYS_ID}

    # No secret configured: events are refused outright.
    assert client.post("/api/servicenow/events", json=body).status_code == 503

    monkeypatch.setenv("SERVICENOW_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    try:
        assert client.post("/api/servicenow/events", json=body).status_code == 401
        wrong = {"x-copilot-secret": "nope"}
        assert client.post("/api/servicenow/events", json=body, headers=wrong).status_code == 401
        ok = client.post(
            "/api/servicenow/events", json=body, headers={"x-copilot-secret": "s3cret"}
        )
        assert ok.status_code == 202
        assert ok.json() == {"status": "imported", "number": "INC1000001"}
        bad = {"sys_id": "not-a-sys-id"}
        assert (
            client.post(
                "/api/servicenow/events", json=bad, headers={"x-copilot-secret": "s3cret"}
            ).status_code
            == 422
        )
    finally:
        monkeypatch.delenv("SERVICENOW_WEBHOOK_SECRET")
        get_settings.cache_clear()
