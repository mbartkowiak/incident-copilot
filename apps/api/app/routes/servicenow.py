import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import telemetry
from app.auth import STAFF, require
from app.config import get_settings
from app.deps import get_servicenow_connector, get_ticket_rate_limiter, get_ticket_service
from app.models import ServiceNowStatus
from app.services.ratelimit import RateLimiter
from app.services.sync import ServiceNowConnector

router = APIRouter(prefix="/api/servicenow", tags=["servicenow"])

Connector = Annotated[ServiceNowConnector | None, Depends(get_servicenow_connector)]

DISABLED = ServiceNowStatus(
    enabled=False,
    instance=None,
    last_sync=None,
    last_error=None,
    imported=0,
    pushed=0,
    updates_applied=0,
)


@router.get("/status", dependencies=[Depends(require(*STAFF))])
def status(connector: Connector) -> ServiceNowStatus:
    return connector.status() if connector else DISABLED


@router.post("/sync", dependencies=[Depends(require("dispatcher"))])
async def sync_now(
    request: Request,
    connector: Connector,
    limiter: Annotated[RateLimiter, Depends(get_ticket_rate_limiter)],
) -> ServiceNowStatus:
    """Run one sync pass now instead of waiting for the poller."""
    if connector is None:
        raise HTTPException(503, "ServiceNow isn't configured.")
    limiter.check(request.client.host if request.client else "unknown")
    if connector.tickets is None:
        get_ticket_service()  # wires the connector to the ticket service
    await run_in_threadpool(connector.sync_once)
    return connector.status()


class IncidentEvent(BaseModel):
    sys_id: str = Field(pattern=r"^[0-9a-f]{32}$")


@router.post("/events", status_code=202)
async def incident_event(
    body: IncidentEvent,
    request: Request,
    connector: Connector,
    limiter: Annotated[RateLimiter, Depends(get_ticket_rate_limiter)],
    x_copilot_secret: Annotated[str, Header()] = "",
) -> dict[str, str | None]:
    """Called by the ServiceNow Business Rule when an incident is created, so it's triaged in
    seconds instead of at the next poll. Authenticated with a shared secret."""
    secret = get_settings().servicenow_webhook_secret
    if connector is None or secret is None or not secret.get_secret_value():
        raise HTTPException(503, "ServiceNow events aren't configured.")
    if not hmac.compare_digest(x_copilot_secret.encode(), secret.get_secret_value().encode()):
        raise HTTPException(401, "Invalid secret.")
    limiter.check(request.client.host if request.client else "unknown")
    if connector.tickets is None:
        get_ticket_service()  # wires the connector to the ticket service
    number = await run_in_threadpool(connector.import_one, body.sys_id)
    telemetry.emit("servicenow_event", sn_sys_id=body.sys_id, imported=number is not None)
    return {"status": "imported" if number else "ignored", "number": number}
