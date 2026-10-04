"""Signs in the demo accounts behind the one-click role buttons.

The demo password stays on the server, so the browser bundle carries no credentials. The call is
Cognito's public InitiateAuth API (no AWS signature needed for a client without a secret).

Visitors get only the ID token. The access and refresh tokens stay here: an access token can
call Cognito's self-service APIs (change attributes, delete the user), which would let one visitor
rename or delete a shared demo account. An expired demo session simply signs in again.
"""

import logging
from typing import Protocol

import requests
from pydantic import BaseModel

log = logging.getLogger(__name__)

TIMEOUT_S = 10


class Tokens(BaseModel):
    id_token: str
    expires_in: int


class SignInFailed(Exception):
    pass


class DemoSignIn(Protocol):
    def sign_in(self, username: str) -> Tokens: ...


class CognitoDemoSignIn:
    def __init__(self, region: str, client_id: str, password: str) -> None:
        self._url = f"https://cognito-idp.{region}.amazonaws.com/"
        self._client_id = client_id
        self._password = password

    def sign_in(self, username: str) -> Tokens:
        try:
            r = requests.post(
                self._url,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
                },
                json={
                    "AuthFlow": "USER_PASSWORD_AUTH",
                    "ClientId": self._client_id,
                    "AuthParameters": {"USERNAME": username, "PASSWORD": self._password},
                },
                timeout=TIMEOUT_S,
            )
        except requests.RequestException as e:
            raise SignInFailed(f"Cognito unreachable: {e}") from None
        if r.status_code != 200:
            raise SignInFailed(f"Cognito HTTP {r.status_code}: {r.text[:200]}")
        result = r.json().get("AuthenticationResult")
        if not result:  # a challenge, e.g. a demo user still on a temporary password
            raise SignInFailed(f"Cognito challenge {r.json().get('ChallengeName')}")
        return Tokens(id_token=result["IdToken"], expires_in=int(result["ExpiresIn"]))
