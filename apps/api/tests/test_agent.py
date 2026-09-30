import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.runner import AgentEvent, TriageAgent, Usage
from app.agent.tools import ToolExecutor
from app.deps import get_agent, get_agent_rate_limiter
from app.main import create_app
from app.models import TriageRequest
from app.services.activity import ActivityService
from app.services.cache import TTLCache
from app.services.ratelimit import RateLimited, RateLimiter
from tests.fakes import FakeWarehouse
from tests.test_triage import FakeRetriever, FakeRouter

DRAFT = {
    "assignment_group": "Network Operations",
    "priority": "3 - Moderate",
    "summary": "Remote user's VPN drops after connecting.",
    "likely_cause": "Corrupted cached portal config after the client upgrade.",
    "resolution_steps": ["Clear the cached portal and re-add it."],
    "citations": ["INC0012345", "KB0010006", "KB9999999"],
    "routing_rationale": "Matches the model and precedent.",
    "related_to_active_spike": False,
    "spike_note": "",
    "clarifying_questions": [],
}


def _usage(inp: int = 100, out: int = 50) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


def tool_use(*calls: tuple[str, str, dict[str, Any]]) -> SimpleNamespace:
    blocks = [SimpleNamespace(type="tool_use", id=i, name=n, input=a) for i, n, a in calls]
    return SimpleNamespace(stop_reason="tool_use", content=blocks, usage=_usage())


def final(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], usage=_usage()
    )


class ScriptedClient:
    def __init__(self, *responses: SimpleNamespace) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def make_agent(client: ScriptedClient, max_turns: int = 6) -> TriageAgent:
    activity = ActivityService(FakeWarehouse(), TTLCache(60))
    executor = ToolExecutor(FakeRouter(), FakeRetriever(), activity)
    return TriageAgent(client, executor, max_turns=max_turns)


REQUEST = TriageRequest(short_description="VPN keeps dropping", description="Working from home")


def test_agent_investigates_then_returns_a_checked_draft() -> None:
    client = ScriptedClient(
        tool_use(
            ("t1", "predict_team", {"ticket_text": "VPN keeps dropping"}),
            ("t2", "search_similar_incidents", {"query": "vpn drops", "limit": 5}),
        ),
        final(json.dumps(DRAFT)),
    )

    events = list(make_agent(client).run(REQUEST))

    assert [e.type for e in events] == [
        "status", "tool_call", "tool_call", "tool_result", "tool_result", "draft", "usage",
    ]  # fmt: skip
    draft = next(e for e in events if e.type == "draft").data
    assert draft["draft"]["assignment_group"] == "Network Operations"
    # KB0010006 came back as the precedent's KB reference; KB9999999 was never retrieved.
    assert draft["grounding"]["ungrounded"] == ["KB9999999"]

    usage = events[-1].data
    assert usage["turns"] == 2
    assert usage["cost_usd"] > 0

    first = client.calls[0]
    assert first["model"] == "claude-opus-5"
    assert first["fallbacks"] == "default"
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert all(t["strict"] for t in first["tools"])
    # The second call carries a tool_result for every tool_use, in one user message.
    results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]


def test_tool_errors_are_returned_to_the_model_not_raised() -> None:
    client = ScriptedClient(
        tool_use(("t1", "check_recent_activity", {"subcategory": "nonsense", "location": "any"})),
        final(json.dumps(DRAFT)),
    )

    events = list(make_agent(client).run(REQUEST))

    result = next(e for e in events if e.type == "tool_result").data
    assert "invalid input" in result["error"]
    sent = client.calls[1]["messages"][-1]["content"][0]
    assert sent["is_error"] is True
    assert any(e.type == "draft" for e in events)


def test_turn_cap_stops_a_looping_agent() -> None:
    client = ScriptedClient(tool_use(("t", "predict_team", {"ticket_text": "x"})))

    events = list(make_agent(client, max_turns=3).run(REQUEST))

    assert len(client.calls) == 3
    assert "No draft after 3 turns" in next(e for e in events if e.type == "error").data["message"]
    assert events[-1].type == "usage"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (final("not json"), "invalid draft"),
        (final("", stop_reason="refusal"), "declined"),
        (final("{}", stop_reason="max_tokens"), "max_tokens"),
    ],
)
def test_bad_endings_become_error_events(response: SimpleNamespace, message: str) -> None:
    events = list(make_agent(ScriptedClient(response)).run(REQUEST))

    assert message in next(e for e in events if e.type == "error").data["message"]


def test_usage_cost_counts_cache_tokens() -> None:
    usage = Usage(
        input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=1_000_000
    )
    # 1M uncached at $5 + 1M cache reads at 0.1x
    assert usage.cost_usd("claude-opus-5") == pytest.approx(5.5)


def test_rate_limiter_enforces_client_and_daily_limits() -> None:
    now = [0.0]
    limiter = RateLimiter(per_client=2, per_client_window_s=60, daily=3, clock=lambda: now[0])

    limiter.check("a")
    limiter.check("a")
    with pytest.raises(RateLimited) as err:
        limiter.check("a")
    assert 0 < err.value.retry_after_s <= 61

    limiter.check("b")
    with pytest.raises(RateLimited, match="daily"):
        limiter.check("c")

    now[0] = 86_401
    limiter.check("a")


class FakeAgent:
    def run(self, request: TriageRequest) -> Iterator[AgentEvent]:
        yield AgentEvent("status", {"run_id": "r1"})
        yield AgentEvent("draft", {"draft": DRAFT, "grounding": {"cited": 3, "ungrounded": []}})


def test_agent_endpoint_streams_server_sent_events() -> None:
    app = create_app()
    app.dependency_overrides[get_agent] = lambda: FakeAgent()
    app.dependency_overrides[get_agent_rate_limiter] = lambda: RateLimiter(5, 60, 100)

    response = TestClient(app).post("/api/triage/agent", json={"short_description": "VPN down"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event:")
    ]
    assert events == ["status", "draft", "done"]


def test_agent_endpoint_emits_one_telemetry_record_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "app.routes.agent.telemetry.emit", lambda event, **f: records.append((event, f))
    )
    app = create_app()
    app.dependency_overrides[get_agent] = lambda: FakeAgent()
    app.dependency_overrides[get_agent_rate_limiter] = lambda: RateLimiter(5, 60, 100)

    TestClient(app).post("/api/triage/agent", json={"short_description": "VPN down"})

    assert len(records) == 1
    event, fields = records[0]
    assert event == "agent_run"
    assert fields["outcome"] == "draft"
    assert fields["team"] == "Network Operations"
    assert fields["citations"] == 3


def test_agent_endpoint_returns_429_when_limited() -> None:
    limiter = RateLimiter(per_client=1, per_client_window_s=60, daily=100)
    app = create_app()
    app.dependency_overrides[get_agent] = lambda: FakeAgent()
    app.dependency_overrides[get_agent_rate_limiter] = lambda: limiter
    client = TestClient(app)

    assert (
        client.post("/api/triage/agent", json={"short_description": "VPN down"}).status_code == 200
    )
    blocked = client.post("/api/triage/agent", json={"short_description": "VPN down"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
