import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app import telemetry
from app.auth import Principal, current_principal
from app.config import get_settings
from app.deps import get_demo_rate_limiter, get_demo_sign_in
from app.services.cognito import DemoSignIn, SignInFailed, Tokens
from app.services.ratelimit import RateLimiter

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)


class DemoAccount(BaseModel):
    username: str
    name: str
    title: str
    role: Literal["employee", "dispatcher", "knowledge_manager"]


# Must match the demo users in infra/terraform/auth.tf. Employees are the Get help personas.
DEMO_ACCOUNTS = [
    DemoAccount(
        username="demo-priya", name="Priya Shah", title="Finance analyst, Remote", role="employee"
    ),
    DemoAccount(
        username="demo-jordan",
        name="Jordan Lee",
        title="Receiving supervisor, Memphis DC",
        role="employee",
    ),
    DemoAccount(
        username="demo-marcus",
        name="Marcus Chen",
        title="Customer service lead, Chicago HQ",
        role="employee",
    ),
    DemoAccount(
        username="demo-ana", name="Ana Torres", title="Shipping clerk, Dallas DC", role="employee"
    ),
    DemoAccount(
        username="demo-dispatcher",
        name="Sam Rivera",
        title="Service desk dispatcher",
        role="dispatcher",
    ),
    DemoAccount(
        username="demo-knowledge",
        name="Alex Morgan",
        title="Knowledge manager",
        role="knowledge_manager",
    ),
]
_BY_USERNAME = {a.username: a for a in DEMO_ACCOUNTS}


class AuthConfig(BaseModel):
    enabled: bool
    region: str
    client_id: str
    domain: str
    demo_accounts: list[DemoAccount]


class DemoSignInRequest(BaseModel):
    username: str


class Me(BaseModel):
    name: str
    site: str
    roles: list[str]
    demo: bool


@router.get("/config")
def config() -> AuthConfig:
    """What the web app needs to sign people in. Public."""
    s = get_settings()
    enabled = bool(s.cognito_user_pool_id)
    demo = enabled and s.cognito_demo_password is not None
    return AuthConfig(
        enabled=enabled,
        region=s.cognito_region,
        client_id=s.cognito_client_id,
        domain=s.cognito_domain,
        demo_accounts=DEMO_ACCOUNTS if demo else [],
    )


@router.post("/demo")
def demo_sign_in(
    body: DemoSignInRequest,
    request: Request,
    signer: Annotated[DemoSignIn | None, Depends(get_demo_sign_in)],
    limiter: Annotated[RateLimiter, Depends(get_demo_rate_limiter)],
) -> Tokens:
    """Sign in as one of the demo accounts, so visitors can try each role in one click."""
    account = _BY_USERNAME.get(body.username)
    if account is None:
        raise HTTPException(404, "No such demo account.")
    if signer is None:
        raise HTTPException(503, "Demo sign-in isn't configured.")
    limiter.check(request.client.host if request.client else "unknown")
    try:
        tokens = signer.sign_in(account.username)
    except SignInFailed as e:
        log.error("demo sign-in failed for %s: %s", account.username, e)
        raise HTTPException(503, "Sign-in is unavailable right now.") from None
    telemetry.emit("demo_sign_in", username=account.username, role=account.role)
    return tokens


@router.get("/me")
def me(principal: Annotated[Principal, Depends(current_principal)]) -> Me:
    return Me(
        name=principal.name,
        site=principal.site,
        roles=sorted(principal.roles),
        demo=principal.demo,
    )
