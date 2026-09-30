from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

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


@router.get("/status")
def status(connector: Connector) -> ServiceNowStatus:
    return connector.status() if connector else DISABLED


@router.post("/sync")
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
