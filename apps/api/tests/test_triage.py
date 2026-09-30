from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.deps import get_triage_service
from app.main import create_app
from app.models import KbArticle, RoutingPrediction, SimilarIncident
from app.services.routing import REVIEW_THRESHOLD, ModelNotReady, to_prediction
from app.services.triage import TriageService


class FakeRouter:
    def __init__(self) -> None:
        self.ready = True
        self.seen: list[str] = []

    def predict(self, text: str) -> RoutingPrediction:
        if not self.ready:
            raise ModelNotReady("loading")
        self.seen.append(text)
        return to_prediction(["Network Operations", "Service Desk"], [0.9, 0.1], "2")

    def status(self) -> str:
        return "ready (v2)" if self.ready else "loading"


class FakeRetriever:
    def similar_incidents(self, text: str, k: int) -> list[SimilarIncident]:
        return [
            SimilarIncident(
                number="INC0012345",
                short_description="VPN won't connect",
                close_notes="Cleared cached portal config. Followed KB0010006.",
                category="network",
                subcategory="vpn",
                assignment_group="Network Operations",
                location="Remote",
                priority_label="3 - Moderate",
                mttr_hours=3.5,
                kb_reference="KB0010006",
                occurrences=14,
                score=0.82,
            )
        ][:k]

    def kb_articles(self, text: str, k: int) -> list[KbArticle]:
        return [
            KbArticle(
                number="KB0010006",
                title="GlobalProtect VPN fails to connect",
                text="# GlobalProtect...",
                kb_category="Network Operations",
                score=0.77,
            )
        ][:k]


@pytest.fixture
def router() -> FakeRouter:
    return FakeRouter()


@pytest.fixture
def client(router: FakeRouter) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_triage_service] = lambda: TriageService(router, FakeRetriever())
    yield TestClient(app)


def test_suggest_combines_prediction_and_precedent(client: TestClient, router: FakeRouter) -> None:
    response = client.post(
        "/api/triage/suggest",
        json={"short_description": "VPN keeps dropping", "description": "Working from home."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["routing"]["assignment_group"] == "Network Operations"
    assert body["routing"]["needs_review"] is False
    assert body["similar_incidents"][0]["kb_reference"] == "KB0010006"
    assert body["kb_articles"][0]["number"] == "KB0010006"
    # The model sees text in the same shape it was trained on.
    assert router.seen == ["VPN keeps dropping\nWorking from home."]


@pytest.mark.parametrize(
    "payload",
    [
        {"short_description": "x"},
        {"short_description": "ok title", "description": "a" * 4001},
        {"description": "missing title"},
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, payload: dict[str, str]) -> None:
    assert client.post("/api/triage/suggest", json=payload).status_code == 422


def test_model_still_loading_returns_503(client: TestClient, router: FakeRouter) -> None:
    router.ready = False

    response = client.post("/api/triage/suggest", json={"short_description": "Printer offline"})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "10"


def test_prediction_ranks_alternatives_and_flags_low_confidence() -> None:
    confident = to_prediction(["A", "B", "C", "D"], [0.1, 0.7, 0.15, 0.05], "3")
    assert confident.assignment_group == "B"
    assert [a.assignment_group for a in confident.alternatives] == ["C", "A"]
    assert confident.needs_review is False

    unsure = to_prediction(["A", "B"], [0.45, 0.55], "3")
    assert unsure.confidence < REVIEW_THRESHOLD
    assert unsure.needs_review is True
