"""A thin ServiceNow Table API client for the incident connector.

Basic auth over HTTPS with a dedicated integration user. Reference fields (caller, location,
assignment group) are looked up by display name and cached, since they rarely change.
"""

import logging
import threading
from typing import Any, Protocol
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

TIMEOUT_S = 20

# ServiceNow incident.state values.
STATE_CODES = {"New": "1", "In Progress": "2", "On Hold": "3", "Resolved": "6", "Closed": "7"}
STATE_NAMES = {code: name for name, code in STATE_CODES.items()} | {"8": "Canceled"}

# The app uses the classic resolution codes. Newer ServiceNow releases renamed them, so each
# maps to the first label the instance actually offers.
CLOSE_CODE_CANDIDATES: dict[str, list[str]] = {
    "Solved (Permanently)": ["Solved (Permanently)", "Solution provided"],
    "Solved Remotely (Permanently)": ["Solved Remotely (Permanently)", "Solution provided"],
    "Solved (Work Around)": ["Solved (Work Around)", "Workaround provided"],
    "Solved Remotely (Work Around)": ["Solved Remotely (Work Around)", "Workaround provided"],
    "Not Solved (Not Reproducible)": ["Not Solved (Not Reproducible)", "No resolution provided"],
    "Closed/Resolved by Caller": ["Closed/Resolved by Caller", "Resolved by caller"],
}

INCIDENT_FIELDS = [
    "sys_id", "number", "sys_created_on", "sys_updated_on", "state", "short_description",
    "description", "caller_id", "location", "contact_type", "category", "impact", "urgency",
    "assignment_group", "close_code", "close_notes", "resolved_at", "correlation_id",
]  # fmt: skip


class ServiceNowError(RuntimeError):
    pass


class ServiceNow(Protocol):
    """The operations the connector needs; tests substitute an in-memory fake."""

    instance: str

    def find(self, table: str, name: str, field: str = "name") -> str | None: ...

    def create_incident(self, fields: dict[str, Any]) -> dict[str, str]: ...

    def update_incident(self, sys_id: str, fields: dict[str, Any]) -> None: ...

    def incidents(self, query: str, limit: int = 50) -> list[dict[str, Any]]: ...

    def close_code(self, app_code: str) -> str: ...


class ServiceNowClient:
    def __init__(self, instance: str, user: str, password: str) -> None:
        self.instance = instance.rstrip("/")
        self._session = requests.Session()
        self._session.auth = (user, password)
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        self._refs: dict[tuple[str, str, str], str | None] = {}
        self._close_codes: list[str] | None = None
        self._lock = threading.Lock()

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.instance}/api/now/{path}"
        try:
            resp = self._session.request(method, url, timeout=TIMEOUT_S, **kwargs)
        except requests.RequestException as e:
            raise ServiceNowError(f"{method} {path}: {type(e).__name__}") from e
        if resp.status_code >= 400:
            detail = resp.text[:300].replace("\n", " ")
            raise ServiceNowError(f"{method} {path}: HTTP {resp.status_code} {detail}")
        return resp.json().get("result") if resp.content else None

    def find(self, table: str, name: str, field: str = "name") -> str | None:
        """sys_id of the record whose `field` equals `name`, cached (including misses)."""
        key = (table, field, name)
        with self._lock:
            if key in self._refs:
                return self._refs[key]
        rows = self._call(
            "GET",
            f"table/{table}",
            params={
                "sysparm_query": f"{field}={name}",
                "sysparm_fields": "sys_id",
                "sysparm_limit": 1,
            },
        )
        sys_id = rows[0]["sys_id"] if rows else None
        with self._lock:
            self._refs[key] = sys_id
        return sys_id

    def create(self, table: str, fields: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = self._call("POST", f"table/{table}", json=fields)
        return result

    def create_incident(self, fields: dict[str, Any]) -> dict[str, str]:
        result = self.create("incident", fields)
        return {"sys_id": result["sys_id"], "number": result["number"]}

    def update_incident(self, sys_id: str, fields: dict[str, Any]) -> None:
        self._call("PATCH", f"table/incident/{quote(sys_id)}", json=fields)

    def incidents(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Incidents matching an encoded query, reference fields as {value, display_value}."""
        rows: list[dict[str, Any]] = self._call(
            "GET",
            "table/incident",
            params={
                "sysparm_query": query,
                "sysparm_fields": ",".join(INCIDENT_FIELDS),
                "sysparm_display_value": "all",
                "sysparm_exclude_reference_link": "true",
                "sysparm_limit": limit,
            },
        )
        return rows

    def close_code(self, app_code: str) -> str:
        """The instance's label for one of the app's resolution codes."""
        if self._close_codes is None:
            try:
                rows = self._call(
                    "GET",
                    "table/sys_choice",
                    params={
                        "sysparm_query": "name=incident^element=close_code^inactive=false",
                        "sysparm_fields": "value",
                    },
                )
                self._close_codes = [r["value"] for r in rows]
            except ServiceNowError:
                log.warning("couldn't read close codes; sending the app's labels")
                self._close_codes = []
        for candidate in CLOSE_CODE_CANDIDATES.get(app_code, [app_code]):
            if not self._close_codes or candidate in self._close_codes:
                return candidate
        return self._close_codes[0]


def value(field: Any) -> str:
    """Raw value of a field returned with sysparm_display_value=all."""
    return str(field.get("value") or "") if isinstance(field, dict) else str(field or "")


def display(field: Any) -> str:
    return str(field.get("display_value") or "") if isinstance(field, dict) else str(field or "")
