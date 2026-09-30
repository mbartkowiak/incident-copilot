import json
import logging
from collections.abc import Iterator
from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

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
    return {"status": "recorded", "run_id": str(body.run_id)}


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


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
        try:
            for event in agent.run(body):
                yield _sse(event.type, event.data)
        except anthropic.RateLimitError:
            yield _sse("error", {"message": "The AI service is busy. Try again in a minute."})
        except anthropic.APIError as e:
            log.error("agent call failed: %s", e)
            yield _sse("error", {"message": "The AI service is unavailable right now."})
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
