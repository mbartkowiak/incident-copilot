from fastapi.testclient import TestClient

from app.main import create_app


def test_agent_eval_reports_are_served() -> None:
    response = TestClient(create_app()).get("/api/quality/agent-evals")

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["summary"]["cases"] == 30
    assert "questions_on_clear_rate" in body["baseline"]["summary"]
