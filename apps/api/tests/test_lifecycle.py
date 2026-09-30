import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import (
    get_lifecycle_service,
    get_lifecycle_writer,
    get_review_rate_limiter,
    get_summary_cache,
)
from app.main import create_app
from app.models import IncidentRow
from app.services.cache import TTLCache
from app.services.lifecycle import (
    MI_LIST_SQL,
    MI_MEMBERS_SQL,
    MI_SQL,
    MI_TIMELINE_SQL,
    PROBLEM_LIST_SQL,
    PROBLEM_MEMBERS_SQL,
    PROBLEM_SQL,
    PROBLEM_WEEKLY_SQL,
    LifecycleService,
    evidence,
)
from app.services.ratelimit import RateLimiter
from app.services.reviews import LifecycleWriter, problem_prompt, review_prompt, sample
from tests.fakes import FakeWarehouse
from tests.test_agent import ScriptedClient, final

MI = {
    "mi_id": "MI20260310-lan",
    "day": "2026-03-10",
    "subcategory": "lan",
    "category": "network",
    "site": "Chicago HQ",
    "started_at": "2026-03-10 08:41:27",
    "restored_at": "2026-03-10 14:29:18",
    "tickets": 85,
    "baseline_daily": 0.11,
    "spike_ratio": 85.0,
    "worst_priority": "2 - High",
    "locations": ["Chicago HQ"],
    "resolving_groups": ["Network Operations"],
    "sla_breaches": 0,
    "avg_mttr_hours": 3.7,
    "top_fix": "Core switch at Chicago HQ failed a supervisor module.",
}

PROBLEM = {
    "problem_id": "PRB20260504-vpn",
    "subcategory": "vpn",
    "category": "network",
    "first_week": "2026-05-04",
    "last_week": "2026-06-08",
    "weeks": 6,
    "tickets": 135,
    "baseline_weekly": 5.83,
    "excess_tickets": 100,
    "hours_to_resolve": 1088.0,
    "sla_breaches": 6,
    "locations": ["Remote"],
    "resolving_groups": ["Network Operations"],
    "top_fix": "GlobalProtect client was on the new version with a corrupted portal config.",
    "top_fix_share": 1.0,
    "top_fix_usual_share": 0.336,
    "major_incident": None,
}


def member(i: int, resolved: bool = True) -> dict[str, Any]:
    return {
        "number": f"INC00{i:05d}",
        "opened_at": f"2026-03-10 {8 + i % 6:02d}:{i % 60:02d}:00",
        "state": "Closed" if resolved else "In Progress",
        "priority_label": "2 - High",
        "short_description": "Network down on floor 3",
        "assignment_group": "Network Operations",
        "subcategory": "lan",
        "location": "Chicago HQ",
        "is_resolved": resolved,
        "sla_breached": False,
        "mttr_hours": 3.5 if resolved else None,
        "close_notes": "Failed over to redundant supervisor." if resolved else None,
    }


RESPONSES = {
    MI_LIST_SQL: [MI],
    MI_SQL: [MI],
    MI_TIMELINE_SQL: [{"hour": "2026-03-10 08:00:00", "opened": 40}],
    MI_MEMBERS_SQL: [member(i) for i in range(20)] + [member(99, resolved=False)],
    PROBLEM_LIST_SQL: [PROBLEM, PROBLEM | {"problem_id": "PRB20260706-wan", "top_fix_share": 0.44,
                                           "top_fix_usual_share": 0.57}],
    PROBLEM_SQL: [PROBLEM],
    PROBLEM_WEEKLY_SQL: [{"week": "2026-05-04", "tickets": 22}],
    PROBLEM_MEMBERS_SQL: [member(1)],
}  # fmt: skip

REVIEW = {
    "headline": "Chicago HQ lost its network on 10 March.",
    "impact": "85 tickets.",
    "timeline": ["08:41 first report"],
    "root_cause": "Supervisor module failure.",
    "resolution": "Failover.",
    "follow_ups": ["Monitor supervisor health."],
}


@pytest.fixture
def warehouse() -> FakeWarehouse:
    return FakeWarehouse(RESPONSES)


@pytest.fixture
def service(warehouse: FakeWarehouse) -> LifecycleService:
    return LifecycleService(warehouse, TTLCache(60))


@pytest.fixture
def claude() -> ScriptedClient:
    return ScriptedClient(final(json.dumps(REVIEW)))


@pytest.fixture
def client(service: LifecycleService, claude: ScriptedClient) -> Iterator[TestClient]:
    app = create_app()
    limiter, cache = RateLimiter(5, 600, 100), TTLCache(60)
    app.dependency_overrides[get_lifecycle_service] = lambda: service
    app.dependency_overrides[get_lifecycle_writer] = lambda: LifecycleWriter(claude, "m")
    app.dependency_overrides[get_review_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_summary_cache] = lambda: cache
    yield TestClient(app)


@pytest.mark.parametrize(
    ("share", "usual", "expected"),
    [(1.0, 0.336, "strong"), (0.4, 0.212, "moderate"), (0.444, 0.573, "weak"), (None, 0.3, "weak"),
     (0.5, 0.0, "weak"), (0.3, 0.1, "moderate")],
)  # fmt: skip
def test_evidence_grades_how_much_one_fix_explains_the_surge(
    share: float | None, usual: float, expected: str
) -> None:
    assert evidence(share, usual) == expected


def test_problems_carry_their_evidence_grade(service: LifecycleService) -> None:
    grades = {p.problem_id: p.evidence for p in service.problems()}

    assert grades == {"PRB20260504-vpn": "strong", "PRB20260706-wan": "weak"}


def test_problem_detail_queries_the_weeks_around_the_surge(
    service: LifecycleService, warehouse: FakeWarehouse
) -> None:
    detail = service.problem("PRB20260504-vpn")

    assert detail.weekly[0].tickets == 22
    params = dict(warehouse.calls)[PROBLEM_WEEKLY_SQL]
    assert params == {"subcategory": "vpn", "first_week": "2026-05-04", "last_week": "2026-06-08"}


def test_endpoints_list_and_open_both_record_types(client: TestClient) -> None:
    assert client.get("/api/major-incidents").json()[0]["site"] == "Chicago HQ"
    mi = client.get("/api/major-incidents/MI20260310-lan").json()
    assert mi["timeline"][0]["opened"] == 40
    assert len(mi["tickets"]) == 21
    assert client.get("/api/problems").json()[0]["evidence"] == "strong"
    assert client.get("/api/problems/PRB20260504-vpn").json()["problem"]["weeks"] == 6


def test_unknown_or_malformed_ids(client: TestClient, warehouse: FakeWarehouse) -> None:
    warehouse.responses[MI_SQL] = []
    assert client.get("/api/major-incidents/MI20990101-lan").status_code == 404
    assert client.get("/api/major-incidents/MI2026;DROP").status_code == 422
    assert client.get("/api/problems/INC0017396").status_code == 422


def test_review_is_drafted_once_from_lakehouse_facts(
    client: TestClient, claude: ScriptedClient
) -> None:
    first = client.post("/api/major-incidents/MI20260310-lan/review")
    second = client.post("/api/major-incidents/MI20260310-lan/review")

    assert first.status_code == 200
    assert first.json()["document"]["root_cause"] == "Supervisor module failure."
    assert second.json()["cached"] is True
    assert len(claude.calls) == 1
    prompt = claude.calls[0]["messages"][0]["content"]
    assert "Tickets: 85 (normally 0.11 a day; 85x)" in prompt
    assert "- 2026-03-10 08:00: 40" in prompt


def test_problem_record_prompt_states_the_fix_lift(service: LifecycleService) -> None:
    prompt = problem_prompt(service.problem("PRB20260504-vpn"))

    assert "That fix resolved 100% of surge tickets, against 34% of this subcategory's" in prompt
    assert "about 100 above baseline" in prompt
    assert "Linked major incident: none" in prompt


def test_problem_record_endpoint(service: LifecycleService) -> None:
    record = {
        "title": "GlobalProtect client upgrade corrupts portal config",
        "problem_statement": "VPN failures surged.",
        "root_cause_hypothesis": "The auto-upgrade.",
        "evidence": ["100% vs 34%"],
        "workaround": "Clear the cached portal.",
        "permanent_fix": "Fix the upgrade package.",
        "next_steps": ["Raise a change."],
    }
    app = create_app()
    claude = ScriptedClient(final(json.dumps(record)))
    app.dependency_overrides[get_lifecycle_service] = lambda: service
    app.dependency_overrides[get_lifecycle_writer] = lambda: LifecycleWriter(claude, "m")
    app.dependency_overrides[get_review_rate_limiter] = lambda: RateLimiter(5, 600, 100)
    app.dependency_overrides[get_summary_cache] = lambda: TTLCache(60)

    response = TestClient(app).post("/api/problems/PRB20260504-vpn/record")

    assert response.status_code == 200
    assert response.json()["document"]["title"].startswith("GlobalProtect")


def test_sample_spreads_across_the_whole_incident() -> None:
    rows = [IncidentRow.model_validate(member(i)) for i in range(40)]

    picked = sample(rows, 8)

    assert len(picked) == 8
    assert picked[0] is rows[0]
    assert picked[-1] is rows[-1]


def test_review_prompt_handles_open_tickets(service: LifecycleService) -> None:
    prompt = review_prompt(service.major_incident("MI20260310-lan"))

    assert "Scope: Chicago HQ" in prompt
    assert "First ticket: 2026-03-10 08:41" in prompt
    assert "| open" in prompt  # the last, unresolved member is described, not crashed on
