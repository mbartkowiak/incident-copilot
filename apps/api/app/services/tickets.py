"""Live tickets: created from conversational intake, triaged on creation, worked by dispatchers.

Tickets live in the `tickets` Delta table; the `incident_queue` view unions them with history,
so the queue, ticket pages, summaries and the knowledge loop treat both alike. Work notes use
the same journal format as the source extract, which keeps timelines and reassignment
tracking identical.
"""

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.models import (
    LiveTicket,
    TicketCreate,
    TicketCreated,
    TicketResolve,
    TriageOutcome,
)
from app.services.retrieval import Retriever
from app.services.routing import Router
from app.services.warehouse import Warehouse

# The company's clock; history timestamps are local wall-clock time in this zone.
COMPANY_TZ = ZoneInfo("America/Chicago")
TS = "%Y-%m-%d %H:%M:%S"

# ServiceNow's default impact x urgency lookup.
PRIORITY_MATRIX: dict[tuple[int, int], int] = {
    (1, 1): 1, (1, 2): 2, (1, 3): 3,
    (2, 1): 2, (2, 2): 3, (2, 3): 4,
    (3, 1): 3, (3, 2): 4, (3, 3): 5,
}  # fmt: skip
PRIORITY_LABELS = {
    1: "1 - Critical",
    2: "2 - High",
    3: "3 - Moderate",
    4: "4 - Low",
    5: "5 - Planning",
}

# At or above this routing confidence a new ticket is assigned without a dispatcher. On held-out
# data the model is ~95% accurate overall and errs mostly below 60% (vague tickets).
AUTO_ASSIGN_CONFIDENCE = 0.85
# A precedent this close supplies the new ticket's category and subcategory.
CATEGORY_MATCH = 0.6

FIRST_NUMBER = 1_000_001  # history uses INC0010001-INC0018xxx

INSERT_SQL = """
INSERT INTO tickets (
  number, opened_at, updated_at, state, caller, location, contact_type, category, subcategory,
  cmdb_ci, impact, urgency, priority, short_description, description, assignment_group,
  suggested_group, triage_confidence, triage_mode, work_notes
) VALUES (
  :number, CAST(:now AS TIMESTAMP), CAST(:now AS TIMESTAMP), :state, :caller, :location,
  :contact_type, nullif(:category, ''), nullif(:subcategory, ''), nullif(:cmdb_ci, ''),
  :impact, :urgency, :priority, :short_description, :description,
  nullif(:assignment_group, ''), :suggested_group, :confidence, :mode, :work_notes
)
"""

MAX_NUMBER_SQL = "SELECT max(CAST(substr(number, 4) AS INT)) AS n FROM tickets"

GET_SQL = """
SELECT number, state, assignment_group, triage_mode, resolved_at IS NOT NULL AS is_resolved
FROM tickets WHERE number = :number
"""

# Every update appends one journal line and stamps updated_at.
ASSIGN_SQL = """
UPDATE tickets SET
  assignment_group = :group,
  triage_mode = CASE WHEN triage_mode = 'review' THEN 'manual' ELSE triage_mode END,
  updated_at = CAST(:now AS TIMESTAMP),
  work_notes = concat_ws(chr(10), work_notes, :line)
WHERE number = :number
"""

NOTE_SQL = """
UPDATE tickets SET
  state = CASE WHEN state = 'New' THEN 'In Progress' ELSE state END,
  updated_at = CAST(:now AS TIMESTAMP),
  work_notes = concat_ws(chr(10), work_notes, :line)
WHERE number = :number
"""

RESOLVE_SQL = """
UPDATE tickets SET
  state = 'Resolved',
  resolved_at = CAST(:now AS TIMESTAMP),
  close_code = :close_code,
  close_notes = :close_notes,
  updated_at = CAST(:now AS TIMESTAMP),
  work_notes = concat_ws(chr(10), work_notes, :line)
WHERE number = :number
"""

LIST_SQL = """
SELECT
  number, CAST(opened_at AS STRING) AS opened_at, state, caller, location,
  CASE priority WHEN 1 THEN '1 - Critical' WHEN 2 THEN '2 - High' WHEN 3 THEN '3 - Moderate'
    WHEN 4 THEN '4 - Low' ELSE '5 - Planning' END AS priority_label,
  short_description, assignment_group, suggested_group, triage_confidence, triage_mode
FROM tickets
WHERE (:review_only = 0 OR (triage_mode = 'review' AND resolved_at IS NULL))
ORDER BY opened_at DESC
LIMIT 100
"""


class TicketNotFound(LookupError):
    pass


class TicketClosed(ValueError):
    pass


def company_now() -> datetime:
    return datetime.now(COMPANY_TZ).replace(tzinfo=None, microsecond=0)


def journal_line(when: datetime, author: str, text: str) -> str:
    """One work-note line; newlines in the text are flattened so the journal stays parseable."""
    return f"{when.strftime(TS)} - {author}: {' '.join(text.split())}"


def is_live(number: str) -> bool:
    digits = number[3:]
    return number.upper().startswith("INC") and digits.isdigit() and int(digits) >= FIRST_NUMBER


class TicketService:
    def __init__(
        self,
        warehouse: Warehouse,
        router: Router,
        retriever: Retriever,
        clock: Callable[[], datetime] = company_now,
    ) -> None:
        self._wh = warehouse
        self._router = router
        self._retriever = retriever
        self._clock = clock
        self._lock = threading.Lock()
        self._next: int | None = None

    def _allocate_number(self) -> str:
        # One API task writes tickets, so an in-process counter seeded from the table is enough.
        # Running several tasks would need a Delta identity column or a sequence service.
        with self._lock:
            if self._next is None:
                rows = self._wh.query(MAX_NUMBER_SQL)
                current = rows[0]["n"] if rows and rows[0]["n"] is not None else FIRST_NUMBER - 1
                self._next = max(int(current) + 1, FIRST_NUMBER)
            number = f"INC{self._next:07d}"
            self._next += 1
            return number

    def triage(self, ticket: TicketCreate) -> TriageOutcome:
        text = "\n".join(p for p in (ticket.short_description, ticket.description) if p)
        prediction = self._router.predict(text)
        precedents = self._retriever.similar_incidents(text, 1)
        match = precedents[0] if precedents and precedents[0].score >= CATEGORY_MATCH else None
        return TriageOutcome(
            suggested_group=prediction.assignment_group,
            confidence=prediction.confidence,
            mode="auto" if prediction.confidence >= AUTO_ASSIGN_CONFIDENCE else "review",
            category=match.category if match else None,
            subcategory=match.subcategory if match else None,
            precedent=match.number if match else None,
        )

    def create(self, ticket: TicketCreate) -> TicketCreated:
        triage = self.triage(ticket)
        priority = PRIORITY_MATRIX[(ticket.impact, ticket.urgency)]
        number = self._allocate_number()
        now = self._clock()
        channel = "the virtual agent" if ticket.contact_type == "virtual_agent" else "self-service"
        lines = [
            journal_line(
                now,
                "Virtual Agent",
                f"Created from a conversation with {ticket.caller} via {channel}.",
            )
        ]
        confidence = f"{triage.confidence:.0%}"
        if triage.mode == "auto":
            lines.append(
                journal_line(
                    now,
                    "Routing model",
                    f"Assigned to {triage.suggested_group} ({confidence} confidence).",
                )
            )
        else:
            lines.append(
                journal_line(
                    now,
                    "Routing model",
                    f"Suggests {triage.suggested_group} ({confidence} confidence). Waiting for dispatcher review.",
                )
            )
        if triage.precedent:
            lines.append(
                journal_line(
                    now,
                    "Routing model",
                    f"Categorized as {triage.category} / {triage.subcategory} from the closest precedent, {triage.precedent}.",
                )
            )
        assigned = triage.suggested_group if triage.mode == "auto" else ""
        self._wh.query(
            INSERT_SQL,
            {
                "number": number,
                "now": now.strftime(TS),
                "state": "New",
                "caller": ticket.caller,
                "location": ticket.location,
                "contact_type": ticket.contact_type,
                "category": triage.category or "",
                "subcategory": triage.subcategory or "",
                "cmdb_ci": ticket.cmdb_ci,
                "impact": ticket.impact,
                "urgency": ticket.urgency,
                "priority": priority,
                "short_description": ticket.short_description,
                "description": ticket.description,
                "assignment_group": assigned,
                "suggested_group": triage.suggested_group,
                "confidence": float(triage.confidence),
                "mode": triage.mode,
                "work_notes": "\n".join(lines),
            },
        )
        return TicketCreated(
            number=number,
            priority_label=PRIORITY_LABELS[priority],
            state="New",
            assignment_group=assigned or None,
            triage=triage,
        )

    def _current(self, number: str) -> dict[str, Any]:
        if not is_live(number):
            raise TicketNotFound(number)
        rows = self._wh.query(GET_SQL, {"number": number.upper()})
        if not rows:
            raise TicketNotFound(number)
        return rows[0]

    def assign(self, number: str, group: str, actor: str = "Dispatcher") -> None:
        current = self._current(number)
        if current["is_resolved"]:
            raise TicketClosed(number)
        previous = current["assignment_group"]
        if previous == group:
            return
        text = (
            f"Not a {previous} issue. Reassigning to {group}."
            if previous
            else f"Reviewed the routing suggestion. Assigned to {group}."
        )
        self._update(ASSIGN_SQL, number, actor, text, {"group": group})

    def add_note(self, number: str, text: str, actor: str = "Dispatcher") -> None:
        if self._current(number)["is_resolved"]:
            raise TicketClosed(number)
        self._update(NOTE_SQL, number, actor, text)

    def resolve(self, number: str, body: TicketResolve, actor: str = "Dispatcher") -> None:
        if self._current(number)["is_resolved"]:
            raise TicketClosed(number)
        self._update(
            RESOLVE_SQL,
            number,
            actor,
            "Resolved. See close notes.",
            {"close_code": body.close_code, "close_notes": body.close_notes},
        )

    def _update(
        self, sql: str, number: str, actor: str, text: str, extra: dict[str, Any] | None = None
    ) -> None:
        now = self._clock()
        self._wh.query(
            sql,
            {
                "number": number.upper(),
                "now": now.strftime(TS),
                "line": journal_line(now, actor, text),
                **(extra or {}),
            },
        )

    def list(self, view: Literal["review", "all"] = "all") -> list[LiveTicket]:
        rows = self._wh.query(LIST_SQL, {"review_only": int(view == "review")})
        return [LiveTicket.model_validate(r) for r in rows]
