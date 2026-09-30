"""The triage agent loop.

A manual loop rather than the SDK tool runner because every step is streamed to the UI as
it happens, and the loop enforces a hard turn cap. Claude calls are non-streaming: each
turn is short, and the UI streams at the granularity of agent steps.
"""

import json
import logging
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.agent.prompt import DRAFT_SCHEMA, SYSTEM
from app.agent.tools import TOOLS, RunContext, ToolError, ToolExecutor, ToolOutput, to_model_content
from app.models import TriageDraft, TriageRequest

log = logging.getLogger(__name__)

# $ per 1M tokens: input, output. Cache writes bill at 1.25x input, reads at 0.1x.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class MessagesClient(Protocol):
    """The slice of `anthropic.Anthropic().beta.messages` the agent uses."""

    def create(self, **kwargs: Any) -> Any: ...


@dataclass
class AgentEvent:
    type: str  # status | tool_call | tool_result | draft | usage | error
    data: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    def cost_usd(self, model: str) -> float:
        price_in, price_out = PRICES.get(model, PRICES["claude-opus-5"])
        billed_in = (
            self.input_tokens + self.cache_write_tokens * 1.25 + self.cache_read_tokens * 0.1
        )
        return (billed_in * price_in + self.output_tokens * price_out) / 1e6


class TriageAgent:
    """Stateless across runs: all per-run state lives in `run`, so one instance serves all
    concurrent requests."""

    def __init__(
        self,
        messages: MessagesClient,
        executor: ToolExecutor,
        model: str = "claude-opus-5",
        effort: str = "medium",
        max_turns: int = 6,
    ) -> None:
        self._messages = messages
        self._executor = executor
        self._model = model
        self._effort = effort
        self._max_turns = max_turns
        self._pool = ThreadPoolExecutor(max_workers=8)

    def run(self, request: TriageRequest) -> Iterator[AgentEvent]:
        run_id = str(uuid.uuid4())
        started = time.perf_counter()
        usage = Usage()
        ctx = RunContext()
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": f"New incident\nShort description: {request.short_description}\n"
                f"Description: {request.description or '(none)'}",
            }
        ]
        yield AgentEvent("status", {"run_id": run_id, "model": self._model})

        turns = 0
        finished = False
        while turns < self._max_turns and not finished:
            turns += 1
            response = self._call(messages)
            usage.add(response.usage)

            if response.stop_reason == "tool_use":
                calls = [b for b in response.content if b.type == "tool_use"]
                for call in calls:
                    yield AgentEvent(
                        "tool_call", {"id": call.id, "name": call.name, "input": call.input}
                    )
                results = []
                for call, outcome in self._pool.map(lambda c: (c, self._execute(c, ctx)), calls):
                    yield _result_event(call, outcome)
                    results.append(_result_block(call, outcome))
                # Append the assistant turn unchanged (it may carry thinking blocks).
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": results})
                continue

            finished = True
            if response.stop_reason == "end_turn":
                yield self._draft_event(response, ctx)
            elif response.stop_reason == "refusal":
                yield AgentEvent("error", {"message": "The model declined this request."})
            else:
                yield AgentEvent(
                    "error", {"message": f"Stopped unexpectedly ({response.stop_reason})."}
                )

        if not finished:
            yield AgentEvent(
                "error", {"message": f"No draft after {self._max_turns} turns; stopping."}
            )

        yield AgentEvent(
            "usage",
            {
                "run_id": run_id,
                "model": self._model,
                "turns": turns,
                "latency_s": round(time.perf_counter() - started, 2),
                "cost_usd": round(usage.cost_usd(self._model), 4),
                **asdict(usage),
            },
        )

    def _call(self, messages: list[dict[str, Any]]) -> Any:
        return self._messages.create(
            model=self._model,
            max_tokens=8000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            tools=TOOLS,
            output_config={
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": DRAFT_SCHEMA},
            },
            cache_control={"type": "ephemeral"},
            messages=messages,
        )

    def _execute(self, call: Any, ctx: RunContext) -> ToolOutput | ToolError:
        try:
            return self._executor.run(call.name, call.input, ctx)
        except ToolError as e:
            return e
        except Exception as e:  # a failing dependency must not kill the run
            log.exception("tool %s failed", call.name)
            return ToolError(f"{call.name} is temporarily unavailable ({type(e).__name__})")

    def _draft_event(self, response: Any, ctx: RunContext) -> AgentEvent:
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            draft = TriageDraft.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError):
            log.error("agent returned an invalid draft: %s", text[:500])
            return AgentEvent("error", {"message": "The agent returned an invalid draft."})
        return AgentEvent(
            "draft",
            {
                "draft": draft.model_dump(),
                "grounding": {
                    "cited": len(draft.citations),
                    "ungrounded": [c for c in draft.citations if c not in ctx.retrieved_ids],
                },
            },
        )


def _result_event(call: Any, outcome: ToolOutput | ToolError) -> AgentEvent:
    if isinstance(outcome, ToolError):
        return AgentEvent("tool_result", {"id": call.id, "name": call.name, "error": str(outcome)})
    return AgentEvent(
        "tool_result",
        {"id": call.id, "name": call.name, "summary": outcome.summary, "data": outcome.data},
    )


def _result_block(call: Any, outcome: ToolOutput | ToolError) -> dict[str, Any]:
    if isinstance(outcome, ToolError):
        return {
            "type": "tool_result",
            "tool_use_id": call.id,
            "content": str(outcome),
            "is_error": True,
        }
    return {"type": "tool_result", "tool_use_id": call.id, "content": to_model_content(outcome)}
