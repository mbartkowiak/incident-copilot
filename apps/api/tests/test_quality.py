from fastapi.testclient import TestClient

from app.main import create_app


def test_agent_eval_reports_are_served() -> None:
    response = TestClient(create_app()).get("/api/quality/agent-evals")

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["summary"]["cases"] == 30
    assert "questions_on_clear_rate" in body["baseline"]["summary"]


def test_feature_eval_reports_are_served_without_model_outputs() -> None:
    response = TestClient(create_app()).get("/api/quality/feature-evals")

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["passed"] is True
    assert {"summary", "kb", "review", "problem", "attachments", "intake"} <= set(
        body["latest"]["summary"]
    )
    assert body["baseline"]["summary"]["review"]["numbers_grounded"] == 0.0
    assert all("output" not in c for c in body["latest"]["cases"])
