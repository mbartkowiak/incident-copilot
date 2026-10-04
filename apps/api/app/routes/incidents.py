from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.agent.prompt import Group
from app.auth import STAFF, require
from app.deps import (
    get_incident_service,
    get_kb_drafter,
    get_kb_rate_limiter,
    get_summarizer,
    get_summary_cache,
    get_summary_rate_limiter,
)
from app.models import IncidentDetail, IncidentList, KbDraftResponse, TicketSummaryResponse
from app.routes.ai_calls import cached_ai_call
from app.services.cache import TTLCache
from app.services.incidents import IncidentNotFound, IncidentService, Status
from app.services.knowledge import DraftResult, KbDrafter, NotResolved
from app.services.ratelimit import RateLimiter
from app.services.summary import TicketSummarizer

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

Incidents = Annotated[IncidentService, Depends(get_incident_service)]
Number = Annotated[str, Path(pattern=r"^[Ii][Nn][Cc]\d{7}$")]
Cache = Annotated[TTLCache, Depends(get_summary_cache)]


def version(ticket: IncidentDetail) -> str:
    """Cache key for AI output about a ticket: live tickets change as they are worked, so a new
    work note or state gets a fresh summary. History never changes."""
    return f"{ticket.number}:{len(ticket.work_notes)}:{ticket.state}"


@router.get("", dependencies=[Depends(require(*STAFF))])
def list_incidents(
    svc: Incidents,
    status: Status = "open",
    priority: Annotated[int, Query(ge=0, le=5)] = 0,
    group: Group | None = None,
    breached: bool = False,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> IncidentList:
    return svc.list(status, priority, group or "", breached, q, limit)


# The ServiceNow app's Copilot button reads tickets and summaries with its shared secret.
@router.get("/{number}", dependencies=[Depends(require(*STAFF, "servicenow"))])
def get_incident(svc: Incidents, number: Number) -> IncidentDetail:
    try:
        return svc.get(number)
    except IncidentNotFound:
        raise HTTPException(status_code=404, detail=f"{number.upper()} not found") from None


@router.post("/{number}/summary", dependencies=[Depends(require(*STAFF, "servicenow"))])
def summarize_incident(
    number: Number,
    request: Request,
    svc: Incidents,
    summarizer: Annotated[TicketSummarizer, Depends(get_summarizer)],
    limiter: Annotated[RateLimiter, Depends(get_summary_rate_limiter)],
    cache: Cache,
) -> TicketSummaryResponse:
    """Claude handoff note (open ticket) or recap (resolved ticket)."""
    ticket = get_incident(svc, number)
    result, fresh = cached_ai_call(
        cache,
        ("summary", version(ticket)),
        limiter,
        request,
        "ticket_summary",
        lambda: summarizer.summarize(ticket),
        lambda r: {
            "state": ticket.state,
            "model": r.model,
            "latency_s": r.latency_s,
            "cost_usd": r.cost_usd,
            "input_tokens": r.usage.input_tokens,
            "output_tokens": r.usage.output_tokens,
        },
    )
    return TicketSummaryResponse(
        number=ticket.number,
        summary=result.value,
        model=result.model,
        cost_usd=result.cost_usd,
        latency_s=result.latency_s,
        cached=not fresh,
    )


@router.post("/{number}/kb-draft", dependencies=[Depends(require(*STAFF))])
def draft_knowledge(
    number: Number,
    request: Request,
    svc: Incidents,
    drafter: Annotated[KbDrafter, Depends(get_kb_drafter)],
    limiter: Annotated[RateLimiter, Depends(get_kb_rate_limiter)],
    cache: Cache,
) -> KbDraftResponse:
    """Is this ticket's fix documented? Returns none / update / new with a draft to review."""
    ticket = get_incident(svc, number)
    if not ticket.resolved_at or not ticket.close_notes:
        raise HTTPException(409, "Only resolved tickets have a fix to document.")

    def call() -> DraftResult:
        try:
            return drafter.draft(ticket)
        except NotResolved as e:
            raise HTTPException(409, str(e)) from None

    drafted, fresh = cached_ai_call(
        cache,
        ("kb_draft", version(ticket)),
        limiter,
        request,
        "kb_draft",
        call,
        lambda d: {
            "action": d.result.value.action,
            "target_kb": d.result.value.target_kb,
            "model": d.result.model,
            "latency_s": d.result.latency_s,
            "cost_usd": d.result.cost_usd,
        },
    )
    return KbDraftResponse(
        number=ticket.number,
        draft=drafted.result.value,
        candidates=drafted.candidates,
        model=drafted.result.model,
        cost_usd=drafted.result.cost_usd,
        latency_s=drafted.result.latency_s,
        cached=not fresh,
    )
