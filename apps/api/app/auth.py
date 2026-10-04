"""Who is calling, and what they may do.

Users sign in with Amazon Cognito (hosted OIDC login, or a one-click demo role brokered by
`routes/auth.py`) and send the ID token as a bearer token. Their Cognito groups are their roles.
The ServiceNow app calls with the shared secret instead and gets a narrow service role.

With no user pool configured (local development, tests), auth is off and every request acts as
a local user holding every role.
"""

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Literal, Protocol

import jwt
from fastapi import Depends, Header, HTTPException, Request

from app.config import get_settings

Role = Literal["employee", "dispatcher", "knowledge_manager", "servicenow"]
USER_ROLES: tuple[Role, ...] = ("employee", "dispatcher", "knowledge_manager")
STAFF: tuple[Role, ...] = ("dispatcher", "knowledge_manager")


@dataclass(frozen=True)
class Principal:
    sub: str
    name: str
    site: str
    roles: frozenset[Role]
    demo: bool = False

    def has_any(self, roles: tuple[Role, ...]) -> bool:
        return bool(self.roles & set(roles))


LOCAL_USER = Principal(sub="local", name="Dispatcher", site="", roles=frozenset(USER_ROLES))
SERVICENOW = Principal(
    sub="servicenow", name="ServiceNow", site="", roles=frozenset({"servicenow"})
)


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Principal: ...


class CognitoVerifier:
    """Verifies Cognito ID tokens against the pool's published signing keys."""

    def __init__(self, region: str, user_pool_id: str, client_id: str) -> None:
        self._issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self._client_id = client_id
        self._keys = jwt.PyJWKClient(f"{self._issuer}/.well-known/jwks.json", lifespan=3600)

    def verify(self, token: str) -> Principal:
        try:
            key = self._keys.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "token_use"]},
            )
        except jwt.PyJWTError as e:
            raise InvalidToken(str(e)) from None
        if claims["token_use"] != "id":
            raise InvalidToken("not an ID token")
        return principal_from_claims(claims)


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    groups = claims.get("cognito:groups") or []
    return Principal(
        sub=str(claims["sub"]),
        name=str(claims.get("name") or claims.get("email") or claims["sub"])[:100],
        site=str(claims.get("custom:site") or ""),
        roles=frozenset(g for g in groups if g in USER_ROLES),
        demo=str(claims.get("custom:demo") or "") == "true",
    )


@lru_cache
def get_verifier() -> TokenVerifier | None:
    s = get_settings()
    if not s.cognito_user_pool_id:
        return None
    return CognitoVerifier(s.cognito_region, s.cognito_user_pool_id, s.cognito_client_id)


def _servicenow_secret_matches(given: str) -> bool:
    secret = get_settings().servicenow_webhook_secret
    if secret is None or not secret.get_secret_value() or not given:
        return False
    return hmac.compare_digest(given.encode(), secret.get_secret_value().encode())


def current_principal(
    request: Request,
    verifier: Annotated[TokenVerifier | None, Depends(get_verifier)],
    authorization: Annotated[str, Header()] = "",
    x_copilot_secret: Annotated[str, Header()] = "",
) -> Principal:
    if verifier is None:
        principal = LOCAL_USER
    elif x_copilot_secret:
        if not _servicenow_secret_matches(x_copilot_secret):
            raise HTTPException(401, "Invalid secret.")
        principal = SERVICENOW
    else:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Sign in to continue.", {"WWW-Authenticate": "Bearer"})
        try:
            principal = verifier.verify(token)
        except InvalidToken:
            raise HTTPException(
                401, "Your session has expired. Sign in again.", {"WWW-Authenticate": "Bearer"}
            ) from None
    request.state.principal = principal
    return principal


def require(*roles: Role) -> Callable[..., Principal]:
    """A dependency that admits callers holding any of `roles`."""

    def check(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if not principal.has_any(roles):
            raise HTTPException(403, "Your role can't do this.")
        return principal

    return check


Employee = Annotated[Principal, Depends(require("employee"))]
Dispatcher = Annotated[Principal, Depends(require("dispatcher"))]
Staff = Annotated[Principal, Depends(require(*STAFF))]
KnowledgeManager = Annotated[Principal, Depends(require("knowledge_manager"))]
