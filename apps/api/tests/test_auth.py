import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import (
    CognitoVerifier,
    InvalidToken,
    Principal,
    get_verifier,
    principal_from_claims,
)
from app.config import get_settings
from app.deps import (
    get_demo_rate_limiter,
    get_demo_sign_in,
    get_incident_service,
    get_kb_draft_store,
    get_ticket_rate_limiter,
    get_ticket_service,
)
from app.main import create_app
from app.models import TicketCreate, TicketCreated, TriageOutcome
from app.services.cache import TTLCache
from app.services.cognito import SignInFailed, Tokens
from app.services.incidents import IncidentService
from app.services.ratelimit import RateLimiter
from tests.fakes import FakeWarehouse

PRIYA = Principal("u-priya", "Priya Shah", "Remote", frozenset({"employee"}), demo=True)
SAM = Principal("u-sam", "Sam Rivera", "", frozenset({"dispatcher"}), demo=True)
ALEX = Principal("u-alex", "Alex Morgan", "", frozenset({"knowledge_manager"}), demo=True)
TOKENS = {"priya": PRIYA, "sam": SAM, "alex": ALEX}
ASSIGN = "/api/tickets/INC1000001/assign"


class FakeVerifier:
    def verify(self, token: str) -> Principal:
        if token not in TOKENS:
            raise InvalidToken("bad token")
        return TOKENS[token]


class FakeTickets:
    def __init__(self) -> None:
        self.created: list[TicketCreate] = []
        self.actions: list[tuple[str, str, str]] = []

    def create(self, body: TicketCreate) -> TicketCreated:
        self.created.append(body)
        triage = TriageOutcome(
            suggested_group="Network Operations",
            confidence=0.9,
            mode="auto",
            category=None,
            subcategory=None,
            precedent=None,
        )
        return TicketCreated(
            number="INC1000001",
            priority_label="3 - Moderate",
            state="New",
            assignment_group="Network Operations",
            triage=triage,
        )

    def assign(self, number: str, group: str, actor: str) -> None:
        self.actions.append(("assign", number, actor))


class FakeSignIn:
    def __init__(self) -> None:
        self.fail = False

    def sign_in(self, username: str) -> Tokens:
        if self.fail:
            raise SignInFailed("Cognito HTTP 400")
        return Tokens(id_token=f"id-{username}", expires_in=3600)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tickets() -> FakeTickets:
    return FakeTickets()


@pytest.fixture
def signer() -> FakeSignIn:
    return FakeSignIn()


@pytest.fixture
def client(tickets: FakeTickets, signer: FakeSignIn) -> Iterator[TestClient]:
    app = create_app()
    writes, demo = RateLimiter(30, 600, 1000), RateLimiter(3, 600, 1000)
    incidents = IncidentService(FakeWarehouse(), TTLCache(60))  # knows no tickets
    app.dependency_overrides[get_verifier] = FakeVerifier
    app.dependency_overrides[get_ticket_service] = lambda: tickets
    app.dependency_overrides[get_ticket_rate_limiter] = lambda: writes
    app.dependency_overrides[get_demo_sign_in] = lambda: signer
    app.dependency_overrides[get_demo_rate_limiter] = lambda: demo
    app.dependency_overrides[get_incident_service] = lambda: incidents
    app.dependency_overrides[get_kb_draft_store] = lambda: None
    yield TestClient(app)


@pytest.fixture
def servicenow_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("SERVICENOW_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    yield "s3cret"
    get_settings.cache_clear()


def test_signing_in_is_required_except_for_health_and_sign_in_itself(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/api/auth/config").status_code == 200
    assert client.get("/api/quality/agent-evals").status_code == 401
    assert client.get("/api/quality/agent-evals", headers=auth("forged")).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_roles_decide_what_each_user_can_do(client: TestClient) -> None:
    # Analytics and queues are for staff, not employees.
    assert client.get("/api/quality/agent-evals", headers=auth("priya")).status_code == 403
    assert client.get("/api/quality/agent-evals", headers=auth("sam")).status_code == 200
    assert client.get("/api/quality/agent-evals", headers=auth("alex")).status_code == 200
    # Only dispatchers work tickets.
    for user in ("alex", "priya"):
        r = client.post(ASSIGN, json={"group": "Network Operations"}, headers=auth(user))
        assert r.status_code == 403
    # Only knowledge managers approve what goes into the knowledge base the agent searches.
    assert client.post("/api/knowledge/drafts", json={}, headers=auth("sam")).status_code == 403
    assert client.post("/api/knowledge/drafts", json={}, headers=auth("alex")).status_code == 422


def test_the_caller_is_the_signed_in_user_whatever_the_request_claims(
    client: TestClient, tickets: FakeTickets
) -> None:
    body = {
        "caller": "Someone Else",
        "location": "Dallas DC",
        "short_description": "VPN drops every hour",
        "impact": 3,
        "urgency": 2,
    }

    assert client.post("/api/tickets", json=body, headers=auth("priya")).status_code == 201
    assert client.post("/api/tickets", json=body, headers=auth("sam")).status_code == 403

    created = tickets.created[0]
    assert (created.caller, created.location) == ("Priya Shah", "Remote")


def test_actions_are_recorded_under_the_signed_in_user(
    client: TestClient, tickets: FakeTickets
) -> None:
    r = client.post(
        "/api/tickets/INC1000001/assign", json={"group": "Service Desk"}, headers=auth("sam")
    )

    assert r.status_code == 200
    assert tickets.actions == [("assign", "INC1000001", "Sam Rivera")]


def test_me_reports_the_identity_the_api_sees(client: TestClient) -> None:
    body = client.get("/api/auth/me", headers=auth("priya")).json()

    assert body == {"name": "Priya Shah", "site": "Remote", "roles": ["employee"], "demo": True}


def test_servicenow_reads_tickets_with_its_secret_and_nothing_else(
    client: TestClient, servicenow_secret: str
) -> None:
    sn = {"X-Copilot-Secret": servicenow_secret}

    # Past the auth check: the ticket simply doesn't exist in the fake warehouse.
    assert client.get("/api/incidents/INC0000001", headers=sn).status_code == 404

    assert client.get("/api/quality/agent-evals", headers=sn).status_code == 403
    assert client.post(ASSIGN, json={"group": "x"}, headers=sn).status_code == 403
    wrong = {"X-Copilot-Secret": "wrong"}
    assert client.get("/api/incidents/INC0000001", headers=wrong).status_code == 401


def test_demo_sign_in_brokers_tokens_for_listed_accounts_only(
    client: TestClient, signer: FakeSignIn
) -> None:
    r = client.post("/api/auth/demo", json={"username": "demo-dispatcher"})
    assert r.status_code == 200
    assert r.json() == {"id_token": "id-demo-dispatcher", "expires_in": 3600}  # no refresh token

    assert client.post("/api/auth/demo", json={"username": "admin"}).status_code == 404
    signer.fail = True
    assert client.post("/api/auth/demo", json={"username": "demo-priya"}).status_code == 503


def test_demo_sign_in_is_rate_limited(client: TestClient) -> None:
    codes = [
        client.post("/api/auth/demo", json={"username": "demo-priya"}).status_code for _ in range(4)
    ]
    assert codes == [200, 200, 200, 429]


def test_auth_is_off_without_a_user_pool() -> None:
    app = create_app()
    client = TestClient(app)

    me = client.get("/api/auth/me").json()
    assert me["name"] == "Dispatcher"
    assert set(me["roles"]) == {"employee", "dispatcher", "knowledge_manager"}
    assert client.get("/api/auth/config").json()["enabled"] is False


def test_claims_map_to_a_principal() -> None:
    p = principal_from_claims(
        {
            "sub": "abc",
            "name": "Sam Rivera",
            "cognito:groups": ["dispatcher", "admins"],
            "custom:demo": "true",
        }
    )

    assert p.roles == {"dispatcher"}  # unknown groups grant nothing
    assert (p.name, p.site, p.demo) == ("Sam Rivera", "", True)


# --- token verification with a real signature -----------------------------------------------

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_pool"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StaticKey:
    key = KEY.public_key()


@pytest.fixture
def verifier(monkeypatch: pytest.MonkeyPatch) -> CognitoVerifier:
    v = CognitoVerifier("us-east-1", "us-east-1_pool", "client-1")
    monkeypatch.setattr(v._keys, "get_signing_key_from_jwt", lambda token: StaticKey())
    return v


def token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "sub": "u-1",
        "iss": ISSUER,
        "aud": "client-1",
        "iat": now,
        "exp": now + 3600,
        "token_use": "id",
        "name": "Priya Shah",
        "custom:site": "Remote",
        "cognito:groups": ["employee"],
        **overrides,
    }
    return jwt.encode(claims, KEY, algorithm="RS256")


def test_a_valid_id_token_is_accepted(verifier: CognitoVerifier) -> None:
    p = verifier.verify(token())

    assert (p.sub, p.name, p.site, p.roles) == ("u-1", "Priya Shah", "Remote", {"employee"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"token_use": "access"},
        {"aud": "another-client"},
        {"iss": "https://cognito-idp.us-east-1.amazonaws.com/other-pool"},
        {"exp": int(time.time()) - 60},
    ],
)
def test_wrong_or_expired_tokens_are_refused(
    verifier: CognitoVerifier, overrides: dict[str, Any]
) -> None:
    with pytest.raises(InvalidToken):
        verifier.verify(token(**overrides))


def test_a_token_signed_by_another_key_is_refused(verifier: CognitoVerifier) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(jwt.decode(token(), options={"verify_signature": False}), other, "RS256")

    with pytest.raises(InvalidToken):
        verifier.verify(forged)
