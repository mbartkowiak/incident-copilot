import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import (
    get_feedback_rate_limiter,
    get_incident_service,
    get_kb_draft_store,
    get_kb_drafter,
    get_kb_rate_limiter,
    get_summary_cache,
)
from app.main import create_app
from app.models import IncidentDetail, KbArticle, KbDecision
from app.services.cache import TTLCache
from app.services.incidents import IncidentService
from app.services.knowledge import (
    INSERT_SQL,
    KbDrafter,
    WarehouseKbDraftStore,
    draft_prompt,
    new_article_number,
    render_article,
)
from app.services.ratelimit import RateLimiter
from tests.fakes import FakeWarehouse
from tests.test_agent import ScriptedClient, final
from tests.test_incidents import DETAIL, OPEN, NumberedWarehouse

KB = KbArticle(
    number="KB0010028",
    title="Warehouse handheld scanners not syncing to WMS",
    text="# Warehouse handheld scanners not syncing to WMS\n\n## Cause\nRoaming drops...",
    kb_category="Warehouse Systems",
    score=0.71,
)

UPDATE = {
    "action": "update",
    "target_kb": "KB0010028",
    "title": "Warehouse handheld scanners not syncing to WMS",
    "symptoms": "Scanners freeze and scans stay pending.",
    "cause": "Aggressive roaming, or an expired device Wi-Fi certificate.",
    "steps": ["Check certificate expiry in MDM.", "Re-enroll devices with expired certificates."],
    "rationale": "KB0010028 covers the symptom but not certificate re-enrollment.",
}


class KbRetriever:
    def __init__(self, articles: list[KbArticle]) -> None:
        self.articles = articles
        self.queries: list[str] = []

    def similar_incidents(self, text: str, k: int) -> list[Any]:
        return []

    def kb_articles(self, text: str, k: int) -> list[KbArticle]:
        self.queries.append(text)
        return self.articles[:k]


class MemoryDraftStore:
    def __init__(self) -> None:
        self.records: list[tuple[KbDecision, IncidentDetail]] = []

    def record(self, decision: KbDecision, ticket: IncidentDetail) -> str:
        self.records.append((decision, ticket))
        return "0f9a3c21-7d4e-4b6a-9c1d-2e3f4a5b6c7d"


@pytest.fixture
def service() -> IncidentService:
    return IncidentService(
        NumberedWarehouse({"INC0017396": DETAIL, "INC0018320": OPEN}), TTLCache(60)
    )


def make_client(
    service: IncidentService, claude: ScriptedClient, store: MemoryDraftStore | None = None
) -> TestClient:
    app = create_app()
    drafter = KbDrafter(claude, KbRetriever([KB]), "claude-opus-5-5")
    limiter, cache = RateLimiter(5, 600, 100), TTLCache(60)
    app.dependency_overrides[get_incident_service] = lambda: service
    app.dependency_overrides[get_kb_drafter] = lambda: drafter
    app.dependency_overrides[get_kb_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_summary_cache] = lambda: cache
    app.dependency_overrides[get_kb_draft_store] = lambda: store or MemoryDraftStore()
    app.dependency_overrides[get_feedback_rate_limiter] = lambda: RateLimiter(20, 600, 1000)
    return TestClient(app)


@pytest.fixture
def claude() -> ScriptedClient:
    return ScriptedClient(final(json.dumps(UPDATE)))


@pytest.fixture
def client(service: IncidentService, claude: ScriptedClient) -> Iterator[TestClient]:
    yield make_client(service, claude)


def test_draft_searches_by_problem_and_fix_and_shows_the_articles(
    service: IncidentService, claude: ScriptedClient
) -> None:
    retriever = KbRetriever([KB])
    ticket = service.get("INC0017396")

    drafted = KbDrafter(claude, retriever, "claude-opus-5-5").draft(ticket)

    assert drafted.result.value.action == "update"
    assert "Re-enrolled device in MDM." in retriever.queries[0]  # the fix is in the query
    prompt = claude.calls[0]["messages"][0]["content"]
    assert "<article number='KB0010028' match=0.71>" in prompt
    assert "Close notes: Re-enrolled device in MDM." in prompt
    # Only investigation notes go in; reassignments and the resolution line are noise.
    assert "Working KB0010028" in prompt
    assert "Reassigning" not in prompt


def test_kb_draft_endpoint_caches_the_result(client: TestClient, claude: ScriptedClient) -> None:
    first = client.post("/api/incidents/INC0017396/kb-draft")
    second = client.post("/api/incidents/INC0017396/kb-draft")

    assert first.status_code == 200
    body = first.json()
    assert body["draft"]["target_kb"] == "KB0010028"
    assert body["candidates"][0]["number"] == "KB0010028"
    assert second.json()["cached"] is True
    assert len(claude.calls) == 1


def test_open_tickets_have_nothing_to_document(client: TestClient) -> None:
    assert client.post("/api/incidents/INC0018320/kb-draft").status_code == 409


@pytest.mark.parametrize(
    "draft",
    [
        UPDATE | {"target_kb": "KB0099999"},  # an article it was never shown
        UPDATE | {"action": "none", "target_kb": ""},
        UPDATE | {"action": "new", "target_kb": "", "steps": []},  # nothing to review
    ],
)
def test_ungrounded_or_empty_drafts_are_rejected(
    service: IncidentService, draft: dict[str, Any]
) -> None:
    client = make_client(service, ScriptedClient(final(json.dumps(draft))))

    assert client.post("/api/incidents/INC0017396/kb-draft").status_code == 502


def test_none_verdict_needs_no_article_content(service: IncidentService) -> None:
    none = UPDATE | {"action": "none", "title": "", "symptoms": "", "cause": "", "steps": []}
    client = make_client(service, ScriptedClient(final(json.dumps(none))))

    assert client.post("/api/incidents/INC0017396/kb-draft").json()["draft"]["action"] == "none"


DECISION: dict[str, Any] = {
    "source_number": "INC0017396",
    "decision": "approved",
    "action": "update",
    "target_kb": "KB0010028",
    "title": UPDATE["title"],
    "symptoms": UPDATE["symptoms"],
    "cause": UPDATE["cause"],
    "steps": UPDATE["steps"],
    "model": "claude-opus-5-5",
}


def test_decision_is_recorded_with_the_ticket_on_record(
    service: IncidentService, claude: ScriptedClient
) -> None:
    store = MemoryDraftStore()
    client = make_client(service, claude, store)

    update = client.post("/api/knowledge/drafts", json=DECISION)
    new = client.post("/api/knowledge/drafts", json=DECISION | {"action": "new", "target_kb": ""})

    assert update.status_code == 201
    assert update.json()["article"] == "KB0010028"
    assert new.json()["article"] == "KBD-0f9a3c21"
    assert store.records[0][1].assignment_group == "Warehouse Systems"


@pytest.mark.parametrize(
    "override",
    [
        {"action": "update", "target_kb": ""},
        {"action": "update", "target_kb": "DROP TABLE"},
        {"action": "new", "target_kb": "KB0010028"},
        {"steps": []},
        {"steps": ["x" * 501]},
        {"title": "hi"},
        {"source_number": "INC1"},
        {"decision": "maybe"},
    ],
)
def test_invalid_decisions_are_rejected(
    service: IncidentService, claude: ScriptedClient, override: dict[str, Any]
) -> None:
    store = MemoryDraftStore()
    client = make_client(service, claude, store)

    assert client.post("/api/knowledge/drafts", json=DECISION | override).status_code == 422
    assert store.records == []


def test_decisions_on_open_or_unknown_tickets_are_refused(
    service: IncidentService, claude: ScriptedClient
) -> None:
    client = make_client(service, claude)

    open_ticket = DECISION | {"source_number": "INC0018320"}
    assert client.post("/api/knowledge/drafts", json=open_ticket).status_code == 409
    unknown = DECISION | {"source_number": "INC0000001"}
    assert client.post("/api/knowledge/drafts", json=unknown).status_code == 404


def test_store_renders_the_article_and_binds_every_value(service: IncidentService) -> None:
    wh = FakeWarehouse()

    draft_id = WarehouseKbDraftStore(wh).record(
        KbDecision.model_validate(DECISION), service.get("INC0017396")
    )

    sql, params = wh.calls[0]
    assert sql == INSERT_SQL
    assert params["draft_id"] == draft_id
    assert params["kb_category"] == "Warehouse Systems"
    assert params["text"].startswith("# Warehouse handheld scanners not syncing to WMS\n")
    assert "1. Check certificate expiry in MDM." in params["text"]
    assert "Scanners freeze" not in sql


def test_rendered_articles_match_the_source_format() -> None:
    text = render_article(" Title ", "Sym.", "Cause.", ["First.", " Second. "])

    assert text == (
        "# Title\n\n## Symptoms\nSym.\n\n## Cause\nCause.\n\n## Resolution\n1. First.\n2. Second.\n"
    )
    assert new_article_number("0f9a3c21-7d4e-4b6a-9c1d-2e3f4a5b6c7d") == "KBD-0f9a3c21"


def test_prompt_says_when_no_articles_matched(service: IncidentService) -> None:
    assert "(none found)" in draft_prompt(service.get("INC0017396"), [])
