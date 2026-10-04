from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app import telemetry
from app.auth import KnowledgeManager
from app.deps import get_feedback_rate_limiter, get_incident_service, get_kb_draft_store
from app.models import KbDecision
from app.services.incidents import IncidentNotFound, IncidentService
from app.services.knowledge import KbDraftStore, new_article_number
from app.services.ratelimit import RateLimiter

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/drafts", status_code=201)
def record_decision(
    body: KbDecision,
    request: Request,
    user: KnowledgeManager,
    svc: Annotated[IncidentService, Depends(get_incident_service)],
    store: Annotated[KbDraftStore, Depends(get_kb_draft_store)],
    limiter: Annotated[RateLimiter, Depends(get_feedback_rate_limiter)],
) -> dict[str, str]:
    """Record a knowledge manager's decision on a draft. Approved drafts reach the knowledge
    base and the agent's search at the next knowledge refresh."""
    limiter.check(request.client.host if request.client else "unknown")
    try:
        ticket = svc.get(body.source_number)
    except IncidentNotFound:
        raise HTTPException(404, f"{body.source_number} not found") from None
    if not ticket.resolved_at:
        raise HTTPException(409, "Only resolved tickets have a fix to document.")

    draft_id = store.record(body, ticket, decided_by=user.name)
    article = body.target_kb if body.action == "update" else new_article_number(draft_id)
    telemetry.emit(
        "kb_decision",
        draft_id=draft_id,
        decision=body.decision,
        action=body.action,
        source_number=body.source_number,
        article=article,
        user=user.name,
    )
    return {"status": "recorded", "draft_id": draft_id, "article": article}
