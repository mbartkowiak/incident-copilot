import logging
from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app import telemetry
from app.agent.prompt import Group
from app.deps import (
    get_incident_service,
    get_summarizer,
    get_summary_cache,
    get_summary_rate_limiter,
)
from app.models import IncidentDetail, IncidentList, TicketSummaryResponse
from app.services.cache import TTLCache
from app.services.incidents import IncidentNotFound, IncidentService, Status
from app.services.ratelimit import RateLimiter
from app.services.summary import SummaryFailed, SummaryResult, TicketSummarizer

router = APIRouter(prefix="/api/incidents", tags=["incidents"])
log = logging.getLogger(__name__)

Incidents = Annotated[IncidentService, Depends(get_incident_service)]
Number = Annotated[str, Path(pattern=r"^[Ii][Nn][Cc]\d{7}$")]


@router.get("")
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


@router.get("/{number}")
def get_incident(svc: Incidents, number: Number) -> IncidentDetail:
    try:
        return svc.get(number)
    except IncidentNotFound:
        raise HTTPException(status_code=404, detail=f"{number.upper()} not found") from None


@router.post("/{number}/summary")
def summarize_incident(
    number: Number,
    request: Request,
    svc: Incidents,
    summarizer: Annotated[TicketSummarizer, Depends(get_summarizer)],
    limiter: Annotated[RateLimiter, Depends(get_summary_rate_limiter)],
    cache: Annotated[TTLCache, Depends(get_summary_cache)],
) -> TicketSummaryResponse:
    """Claude summary of one ticket. Tickets don't change, so each is summarized once and
    served from cache after that; only fresh summaries count against the rate limit."""
    ticket = get_incident(svc, number)
    fresh = False

    def generate() -> SummaryResult:
        nonlocal fresh
        limiter.check(request.client.host if request.client else "unknown")
        fresh = True
        try:
            result = summarizer.summarize(ticket)
        except anthropic.APIError as e:
            log.error("summary call failed: %s", e)
            telemetry.emit("ticket_summary", number=ticket.number, outcome="anthropic_error")
            raise HTTPException(503, "The AI service is unavailable right now.") from None
        except SummaryFailed as e:
            telemetry.emit("ticket_summary", number=ticket.number, outcome="failed", error=str(e))
            raise HTTPException(502, "Couldn't summarize this ticket.") from None
        telemetry.emit(
            "ticket_summary",
            number=ticket.number,
            outcome="summary",
            state=ticket.state,
            model=result.model,
            latency_s=result.latency_s,
            cost_usd=result.cost_usd,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
        return result

    result: SummaryResult = cache.get_or_set(("summary", ticket.number), generate)
    return TicketSummaryResponse(
        number=ticket.number,
        summary=result.summary,
        model=result.model,
        cost_usd=result.cost_usd,
        latency_s=result.latency_s,
        cached=not fresh,
    )
