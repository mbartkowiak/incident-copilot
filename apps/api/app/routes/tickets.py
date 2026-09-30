import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app import telemetry
from app.deps import (
    get_intake_agent,
    get_intake_rate_limiter,
    get_ticket_rate_limiter,
    get_ticket_service,
)
from app.models import (
    IntakeChatRequest,
    IntakeTurnResponse,
    LiveTicket,
    TicketAssign,
    TicketCreate,
    TicketCreated,
    TicketNote,
    TicketResolve,
)
from app.services.intake_chat import IntakeAgent
from app.services.ratelimit import RateLimiter
from app.services.structured import StructuredCallFailed
from app.services.tickets import TicketClosed, TicketNotFound, TicketService

router = APIRouter(prefix="/api", tags=["tickets"])
log = logging.getLogger(__name__)

Tickets = Annotated[TicketService, Depends(get_ticket_service)]
Writes = Annotated[RateLimiter, Depends(get_ticket_rate_limiter)]
Number = Annotated[str, Path(pattern=r"^[Ii][Nn][Cc]\d{7}$")]


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/intake/chat")
def intake_chat(
    body: IntakeChatRequest,
    request: Request,
    agent: Annotated[IntakeAgent, Depends(get_intake_agent)],
    limiter: Annotated[RateLimiter, Depends(get_intake_rate_limiter)],
) -> IntakeTurnResponse:
    """One virtual-agent turn. The client sends the whole transcript each time."""
    if body.messages[0].role != "user" or body.messages[-1].role != "user":
        raise HTTPException(422, "The conversation must start and end with the employee.")
    limiter.check(_client(request))
    try:
        result = agent.turn(body.caller, body.location, body.messages)
    except anthropic.APIError as e:
        log.error("intake chat failed: %s", e)
        telemetry.emit("intake_turn", outcome="anthropic_error")
        raise HTTPException(503, "The virtual agent is unavailable right now.") from None
    except StructuredCallFailed as e:
        telemetry.emit("intake_turn", outcome="failed", error=str(e))
        raise HTTPException(502, "The virtual agent couldn't answer. Try again.") from None
    telemetry.emit(
        "intake_turn",
        outcome="ok",
        employee_messages=sum(m.role == "user" for m in body.messages),
        ready=result.value.ready,
        model=result.model,
        latency_s=result.latency_s,
        cost_usd=result.cost_usd,
    )
    return IntakeTurnResponse(
        turn=result.value, model=result.model, cost_usd=result.cost_usd, latency_s=result.latency_s
    )


@router.post("/tickets", status_code=201)
def create_ticket(
    body: TicketCreate, request: Request, svc: Tickets, limiter: Writes
) -> TicketCreated:
    """Create a ticket and triage it: high-confidence routing assigns it, the rest wait for
    a dispatcher."""
    limiter.check(_client(request))
    created = svc.create(body)
    telemetry.emit(
        "ticket_created",
        number=created.number,
        contact_type=body.contact_type,
        priority=created.priority_label,
        mode=created.triage.mode,
        suggested_group=created.triage.suggested_group,
        confidence=created.triage.confidence,
        categorized=created.triage.subcategory is not None,
    )
    return created


@router.get("/tickets")
def list_tickets(svc: Tickets, view: Literal["review", "all"] = "all") -> list[LiveTicket]:
    """Tickets created in the app; `view=review` is the dispatcher's review queue."""
    return svc.list(view)


@contextmanager
def _ticket_errors(number: str) -> Iterator[None]:
    try:
        yield
    except TicketNotFound:
        raise HTTPException(404, f"{number.upper()} is not a live ticket") from None
    except TicketClosed:
        raise HTTPException(409, f"{number.upper()} is already resolved") from None


@router.post("/tickets/{number}/assign")
def assign_ticket(
    number: Number,
    body: TicketAssign,
    request: Request,
    svc: Tickets,
    limiter: Writes,
) -> dict[str, str]:
    limiter.check(_client(request))
    with _ticket_errors(number):
        svc.assign(number, body.group)
    telemetry.emit("ticket_assigned", number=number.upper(), group=body.group)
    return {"status": "assigned", "number": number.upper()}


@router.post("/tickets/{number}/notes")
def add_note(
    number: Number,
    body: TicketNote,
    request: Request,
    svc: Tickets,
    limiter: Writes,
) -> dict[str, str]:
    limiter.check(_client(request))
    with _ticket_errors(number):
        svc.add_note(number, body.text)
    return {"status": "noted", "number": number.upper()}


@router.post("/tickets/{number}/resolve")
def resolve_ticket(
    number: Number,
    body: TicketResolve,
    request: Request,
    svc: Tickets,
    limiter: Writes,
) -> dict[str, str]:
    limiter.check(_client(request))
    with _ticket_errors(number):
        svc.resolve(number, body)
    telemetry.emit("ticket_resolved", number=number.upper(), close_code=body.close_code)
    return {"status": "resolved", "number": number.upper()}
