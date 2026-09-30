from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_feedback_rate_limiter, get_feedback_store
from app.main import create_app
from app.models import TriageFeedback
from app.services.feedback import INSERT_SQL, WarehouseFeedbackStore
from app.services.ratelimit import RateLimiter
from tests.fakes import FakeWarehouse

FEEDBACK: dict[str, Any] = {
    "run_id": "5500171b-59f0-42ff-acb3-816e30614d2a",
    "decision": "edited",
    "short_description": "Handheld scanners not syncing",
    "description": "RF guns at receiving say host not reachable",
    "suggested_group": "Warehouse Systems",
    "final_group": "Network Operations",
    "priority": "2 - High",
    "resolution": "AP at receiving was down; bounced PoE port.",
    "citations": ["KB0010028", "INC0017432"],
    "agent_model": "claude-opus-5",
}


class MemoryStore:
    def __init__(self) -> None:
        self.records: list[TriageFeedback] = []

    def record(self, feedback: TriageFeedback) -> None:
        self.records.append(feedback)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_feedback_store] = lambda: store
    app.dependency_overrides[get_feedback_rate_limiter] = lambda: RateLimiter(20, 600, 1000)
    return TestClient(app)


def test_feedback_is_recorded(client: TestClient, store: MemoryStore) -> None:
    response = client.post("/api/triage/feedback", json=FEEDBACK)

    assert response.status_code == 201
    assert store.records[0].final_group == "Network Operations"


@pytest.mark.parametrize(
    "override",
    [
        {"final_group": "Some Other Team"},
        {"decision": "maybe"},
        {"run_id": "not-a-uuid"},
        {"priority": "urgent"},
        {"citations": [f"KB{i}" for i in range(21)]},
    ],
)
def test_invalid_feedback_is_rejected(
    client: TestClient, store: MemoryStore, override: dict[str, Any]
) -> None:
    assert client.post("/api/triage/feedback", json={**FEEDBACK, **override}).status_code == 422
    assert store.records == []


def test_warehouse_store_uses_bound_parameters() -> None:
    wh = FakeWarehouse()

    WarehouseFeedbackStore(wh).record(TriageFeedback.model_validate(FEEDBACK))

    sql, params = wh.calls[0]
    assert sql == INSERT_SQL
    assert params["citations"] == "KB0010028,INC0017432"
    assert params["run_id"] == FEEDBACK["run_id"]
    # Values travel as parameters, never inside the SQL text.
    assert "Handheld" not in sql
