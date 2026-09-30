import json
import logging
from collections.abc import Iterator
from typing import Annotated, Any

import anthropic
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app import telemetry
from app.agent.runner import TriageAgent
from app.deps import (
    get_agent,
    get_agent_rate_limiter,
    get_feedback_rate_limiter,
    get_feedback_store,
)
from app.models import TriageFeedback, TriageRequest
from app.services.feedback import FeedbackStore
from app.services.ratelimit import RateLimiter

router = APIRouter(prefix="/api/triage", tags=["agent"])
log = logging.getLogger(__name__)


@router.post("/feedback", status_code=201)
def record_feedback(
    body: TriageFeedback,
    request: Request,
    store: Annotated[FeedbackStore, Depends(get_feedback_store)],
    limiter: Annotated[RateLimiter, Depends(get_feedback_rate_limiter)],
) -> dict[str, str]:
    """Record the dispatcher's decision on a draft. Approved drafts become precedents."""
    limiter.check(request.client.host if request.client else "unknown")
    store.record(body)
    telemetry.emit(
        "triage_feedback",
        run_id=str(body.run_id),
        decision=body.decision,
        suggested_group=body.suggested_group,
        final_group=body.final_group,
        team_changed=body.suggested_group != body.final_group,
    )
    return {"status": "recorded", "run_id": str(body.run_id)}


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _record(run: dict[str, Any], event_type: str, data: dict[str, Any]) -> None:
    """Fold streamed agent events into one telemetry record per run."""
    if event_type == "tool_call":
        run["tool_calls"] += 1
    elif event_type == "tool_result" and "error" in data:
        run["tool_errors"] += 1
    elif event_type == "draft":
        draft = data["draft"]
        run.update(
            outcome="draft",
            team=draft["assignment_group"],
            priority=draft["priority"],
            citations=len(draft["citations"]),
            ungrounded=len(data["grounding"]["ungrounded"]),
            clarifying_questions=len(draft["clarifying_questions"]),
            related_to_active_spike=draft["related_to_active_spike"],
        )
    elif event_type == "error":
        run.update(outcome="error", error=data.get("message"))
    elif event_type == "usage":
        run.update(data)


@router.post("/agent")
def run_agent(
    body: TriageRequest,
    request: Request,
    agent: Annotated[TriageAgent, Depends(get_agent)],
    limiter: Annotated[RateLimiter, Depends(get_agent_rate_limiter)],
) -> StreamingResponse:
    """Run the triage agent and stream its steps as Server-Sent Events."""
    limiter.check(request.client.host if request.client else "unknown")

    def stream() -> Iterator[str]:
        run: dict[str, Any] = {"outcome": "incomplete", "tool_calls": 0, "tool_errors": 0}
        try:
            for event in agent.run(body):
                _record(run, event.type, event.data)
                yield _sse(event.type, event.data)
        except anthropic.RateLimitError:
            run["outcome"] = "anthropic_rate_limited"
            yield _sse("error", {"message": "The AI service is busy. Try again in a minute."})
        except anthropic.APIError as e:
            run["outcome"] = "anthropic_error"
            log.error("agent call failed: %s", e)
            yield _sse("error", {"message": "The AI service is unavailable right now."})
        finally:
            telemetry.emit("agent_run", **run)
        yield _sse("done", {})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # Content-Encoding stops proxies from buffering the stream to compress it.
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )
