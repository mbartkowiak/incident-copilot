"""The ServiceNow connector: keep live tickets and ServiceNow incidents in step.

- Outbound (the Mirror protocol): a ticket created in the app is created in ServiceNow with
  `correlation_id` set to the app's number, and assignments, notes and resolutions follow it.
- Inbound (`sync_once`, run by a background poller):
  - Incidents raised in ServiceNow are imported and triaged. The connector writes back an
    AI triage work note and, when the routing model is confident and nobody has assigned
    the incident yet, the assignment group.
  - State, assignment and resolution changes made in ServiceNow are applied to the app's copy.
    ServiceNow is the system of record.

ServiceNow being slow or down never blocks the app: tickets are saved first, failures are
logged, and app tickets that didn't reach ServiceNow are pushed on a later sync.
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Any, cast

from app import telemetry
from app.models import Level, ServiceNowStatus, TicketFields, TicketResolve, TriageOutcome
from app.services.servicenow import (
    STATE_CODES,
    STATE_NAMES,
    ServiceNow,
    ServiceNowError,
    display,
    value,
)
from app.services.tickets import TicketService, triage_note

CORRELATION_DISPLAY = "Incident Copilot"
AUTHOR = "Incident Copilot"
# Incidents raised in ServiceNow within this window are candidates for import. A relative
# window avoids comparing timestamps across the instance's and the app's time zones.
IMPORT_WINDOW = "@hour@ago@24"
UPDATE_WINDOW = "@minute@ago@15"
# The incident form's default category; replacing it doesn't override a human choice.
DEFAULT_CATEGORY = "inquiry"

log = logging.getLogger(__name__)


def _level(raw: str) -> Level:
    """ServiceNow impact/urgency are '1'-'3'; anything else counts as the lowest."""
    return cast(Level, int(raw)) if raw in ("1", "2", "3") else 3


class ServiceNowConnector:
    def __init__(self, client: ServiceNow) -> None:
        self._sn = client
        self.tickets: TicketService | None = None  # set once both exist; they reference each other
        self._lock = threading.Lock()
        self._last_sync: datetime | None = None
        self._last_error: str | None = None
        self._counts = {"imported": 0, "pushed": 0, "updates_applied": 0}

    # --- status -----------------------------------------------------------------------------

    def status(self) -> ServiceNowStatus:
        return ServiceNowStatus(
            enabled=True,
            instance=self._sn.instance,
            last_sync=self._last_sync,
            last_error=self._last_error,
            **self._counts,
        )

    def incident_url(self, sn_sys_id: str) -> str:
        return f"{self._sn.instance}/incident.do?sys_id={sn_sys_id}"

    def _failed(self, what: str, error: Exception) -> None:
        self._last_error = f"{what}: {error}"
        log.warning("servicenow %s failed: %s", what, error)
        telemetry.emit("servicenow_error", action=what, error=str(error)[:300])

    # --- outbound (Mirror) --------------------------------------------------------------------

    def _references(self, caller: str, location: str, group: str) -> dict[str, str]:
        refs = {
            "caller_id": self._sn.find("sys_user", caller) if caller else None,
            "location": self._sn.find("cmn_location", location) if location else None,
            "assignment_group": self._sn.find("sys_user_group", group) if group else None,
        }
        return {k: v for k, v in refs.items() if v}

    def created(
        self,
        number: str,
        ticket: TicketFields,
        triage: TriageOutcome,
        priority: int,
        current_group: str | None = None,
        current_state: str = "New",
    ) -> str | None:
        """Create the ServiceNow incident. A catch-up push passes the ticket's current group and
        state, since a dispatcher may have worked it while ServiceNow was unreachable."""
        group = (
            current_group
            if current_group is not None
            else (triage.suggested_group if triage.mode == "auto" else "")
        )
        notes = [
            f"{AUTHOR}: created from {ticket.caller}'s conversation with the virtual agent.",
            f"{AUTHOR} routing: {triage_note(triage)}",
        ]
        try:
            fields: dict[str, Any] = {
                "short_description": ticket.short_description,
                "description": ticket.description,
                "impact": str(ticket.impact),
                "urgency": str(ticket.urgency),
                "contact_type": ticket.contact_type,
                "correlation_id": number,
                "correlation_display": CORRELATION_DISPLAY,
                "work_notes": "\n".join(notes),
                **self._references(ticket.caller, ticket.location, group),
            }
            if triage.category:
                fields["category"] = triage.category
            if current_state in STATE_CODES and current_state != "New":
                fields["state"] = STATE_CODES[current_state]
            if not fields.get("caller_id"):
                fields["description"] = (
                    f"Caller: {ticket.caller}, {ticket.location}\n\n{ticket.description}"
                )
            created = self._sn.create_incident(fields)
        except ServiceNowError as e:
            self._failed(f"create {number}", e)
            return None
        assert self.tickets is not None
        self.tickets.link(number, created["sys_id"], created["number"])
        self._counts["pushed"] += 1
        telemetry.emit("servicenow_pushed", number=number, sn_number=created["number"])
        return created["number"]

    def _patch(self, ticket: dict[str, Any], fields: dict[str, Any], what: str) -> None:
        sn_sys_id = ticket.get("sn_sys_id")
        if not sn_sys_id:
            return  # not in ServiceNow yet; the next sync creates it with current state
        try:
            self._sn.update_incident(sn_sys_id, fields)
        except ServiceNowError as e:
            self._failed(f"{what} {ticket['number']}", e)

    def assigned(self, ticket: dict[str, Any], group: str, note: str) -> None:
        refs = self._references("", "", group)
        self._patch(ticket, {**refs, "work_notes": note}, "assign")

    def noted(self, ticket: dict[str, Any], note: str) -> None:
        fields = {"work_notes": note}
        if ticket.get("state") == "New":
            fields["state"] = STATE_CODES["In Progress"]
        self._patch(ticket, fields, "note")

    def resolved(self, ticket: dict[str, Any], body: TicketResolve, note: str) -> None:
        fields = {
            "state": STATE_CODES["Resolved"],
            "close_code": self._sn.close_code(body.close_code),
            "close_notes": body.close_notes,
            "work_notes": note,
        }
        self._patch(ticket, fields, "resolve")

    # --- inbound ------------------------------------------------------------------------------

    def sync_once(self) -> None:
        """One pass: push unlinked app tickets, import new ServiceNow incidents, pull changes."""
        assert self.tickets is not None
        if not self._lock.acquire(blocking=False):
            return  # a pass is already running
        try:
            self._last_error = None
            self._push_unlinked()
            self._import_new()
            self._pull_updates()
            self._last_sync = datetime.now(UTC)
        except ServiceNowError as e:
            self._failed("sync", e)
        finally:
            self._lock.release()

    def _push_unlinked(self) -> None:
        assert self.tickets is not None
        for row in self.tickets.unlinked():
            ticket = TicketFields(
                caller=row["caller"] or "",
                location=row["location"] or "",
                contact_type=row["contact_type"] or "virtual_agent",
                short_description=row["short_description"],
                description=row["description"] or "",
                impact=_level(str(row["impact"])),
                urgency=_level(str(row["urgency"])),
            )
            triage = TriageOutcome(
                suggested_group=row["suggested_group"] or "",
                confidence=float(row["triage_confidence"] or 0),
                mode="auto" if row["triage_mode"] == "auto" else "review",
                category=row["category"],
                subcategory=row["subcategory"],
                precedent=None,
            )
            self.created(
                row["number"],
                ticket,
                triage,
                0,
                current_group=row["assignment_group"] or "",
                current_state=row["state"] or "New",
            )

    def _import_new(self) -> None:
        assert self.tickets is not None
        query = f"active=true^correlation_idISEMPTY^sys_created_onRELATIVEGT{IMPORT_WINDOW}^ORDERBYsys_created_on"
        for inc in self._sn.incidents(query, limit=20):
            sys_id = value(inc["sys_id"])
            if self.tickets.by_servicenow_id(sys_id):
                continue
            ticket = TicketFields(
                caller=display(inc["caller_id"])[:100],
                location=display(inc["location"])[:100],
                contact_type=value(inc["contact_type"])[:40],
                short_description=(value(inc["short_description"]) or "(no short description)")[
                    :200
                ],
                description=value(inc["description"])[:4000],
                impact=_level(value(inc["impact"])),
                urgency=_level(value(inc["urgency"])),
            )
            sn_number = value(inc["number"])
            created = self.tickets.create(
                ticket, origin="servicenow", sn_sys_id=sys_id, sn_number=sn_number
            )
            triage = created.triage
            fields: dict[str, Any] = {
                "correlation_id": created.number,
                "correlation_display": CORRELATION_DISPLAY,
                "work_notes": self._triage_work_note(triage),
            }
            # Only fill what nobody in ServiceNow has chosen: an empty group, the default category.
            if triage.mode == "auto" and not value(inc["assignment_group"]):
                fields.update(self._references("", "", triage.suggested_group))
            if triage.category and value(inc.get("category")) in ("", DEFAULT_CATEGORY):
                fields["category"] = triage.category
            self._sn.update_incident(sys_id, fields)
            self._counts["imported"] += 1
            telemetry.emit(
                "servicenow_imported",
                number=created.number,
                sn_number=sn_number,
                mode=triage.mode,
                confidence=triage.confidence,
            )

    @staticmethod
    def _triage_work_note(triage: TriageOutcome) -> str:
        lines = [f"{AUTHOR} triage: {triage_note(triage)}"]
        if triage.precedent:
            lines.append(
                f"Closest precedent: {triage.precedent} ({triage.category} / {triage.subcategory})."
            )
        return "\n".join(lines)

    def _pull_updates(self) -> None:
        assert self.tickets is not None
        query = f"correlation_idSTARTSWITHINC1^sys_updated_onRELATIVEGT{UPDATE_WINDOW}"
        for inc in self._sn.incidents(query, limit=50):
            local = self.tickets.by_servicenow_id(value(inc["sys_id"]))
            if local is None:
                continue
            state = STATE_NAMES.get(value(inc["state"]), local["state"])
            group = display(inc["assignment_group"])
            changes = []
            if state != local["state"]:
                changes.append(f"state is now {state}")
            if group and group != (local["assignment_group"] or ""):
                changes.append(f"assignment group is now {group}")
            if not changes:
                continue  # includes the echo of the app's own updates
            resolved_now = state in ("Resolved", "Closed") and not local["is_resolved"]
            self.tickets.apply_external(
                local["number"],
                state=state,
                group=group or (local["assignment_group"] or ""),
                close_code=display(inc["close_code"])
                if resolved_now
                else (local["close_code"] or ""),
                close_notes=value(inc["close_notes"])
                if resolved_now
                else (local["close_notes"] or ""),
                actor="ServiceNow",
                text=f"Updated in {value(inc['number'])}: {'; '.join(changes)}.",
            )
            self._counts["updates_applied"] += 1


class Poller:
    """Runs sync_once every `interval` seconds on a daemon thread."""

    def __init__(self, connector: ServiceNowConnector, interval: float) -> None:
        self._connector = connector
        self._interval = interval
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, name="servicenow-sync", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._connector.sync_once()
            except Exception:  # never let the loop die
                log.exception("servicenow sync crashed")
