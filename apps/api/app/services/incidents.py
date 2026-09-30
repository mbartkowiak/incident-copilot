"""Incident queue and ticket detail over incident_queue: history plus live tickets.

Fixed SQL templates with bound parameters only, like the dashboard metrics.
"""

import re
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from app.models import BreachRisk, IncidentDetail, IncidentList, IncidentRow, SlaStatus, WorkNote
from app.services.cache import TTLCache
from app.services.tickets import is_live
from app.services.warehouse import Warehouse

Status = Literal["open", "resolved", "all"]

# Timestamps are cast to strings so they come back as naive local wall-clock times.
LIST_SQL = """
SELECT
  number,
  CAST(opened_at AS STRING) AS opened_at,
  state,
  priority_label,
  short_description,
  assignment_group,
  subcategory,
  location,
  is_resolved,
  sla_breached,
  mttr_hours
FROM incident_queue
WHERE (:status = 'all'
       OR (:status = 'open' AND NOT is_resolved)
       OR (:status = 'resolved' AND is_resolved))
  AND (:priority = 0 OR priority = :priority)
  AND (:assignment_group = '' OR assignment_group = :assignment_group)
  AND (:breached_only = 0 OR sla_breached)
  AND (:q = '' OR number = upper(:q) OR short_description ILIKE concat('%', :q, '%'))
ORDER BY opened_at DESC
LIMIT :limit
"""

AS_OF_SQL = "SELECT CAST(max(opened_date) AS STRING) AS as_of FROM gold_incident_facts"

DETAIL_SQL = """
SELECT
  number,
  state,
  CAST(opened_at AS STRING) AS opened_at,
  CAST(resolved_at AS STRING) AS resolved_at,
  CAST(closed_at AS STRING) AS closed_at,
  priority,
  priority_label,
  short_description,
  description,
  category,
  subcategory,
  cmdb_ci,
  location,
  contact_type,
  assignment_group,
  assigned_to,
  reassignment_count,
  reopen_count,
  close_code,
  close_notes,
  work_notes,
  sla_target_hours,
  sla_breached,
  mttr_hours,
  is_resolved,
  source,
  live_elapsed_hours,
  caller_id,
  (SELECT min(m.mi_id) FROM major_incident_members m WHERE m.number = f.number)
    AS major_incident,
  (SELECT min(p.problem_id) FROM problem_members p WHERE p.number = f.number) AS problem
FROM incident_queue f
WHERE number = :number
"""

# Resolved history at this priority: how often this subcategory breached, and how routing
# changed the odds.
RISK_SQL = """
SELECT
  count_if(subcategory = :subcategory) AS similar_tickets,
  count_if(subcategory = :subcategory AND sla_breached) AS similar_breaches,
  avg(CAST(sla_breached AS INT)) AS priority_rate,
  avg(CASE WHEN was_reassigned THEN CAST(sla_breached AS INT) END) AS misrouted_rate,
  avg(CASE WHEN NOT was_reassigned THEN CAST(sla_breached AS INT) END) AS routed_right_rate
FROM gold_incident_facts
WHERE is_resolved AND priority = :priority
"""

# Pseudo-count pulling rare subcategories toward their priority's rate (see ml/sla/model.py,
# where this lookup was chosen over a trained classifier).
RISK_SMOOTHING = 5

_NOTE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - ([^:]+): (.+)$")
_REASSIGN_RE = re.compile(r"^Not a (.+) issue\. Reassigning to")


class IncidentNotFound(LookupError):
    pass


def parse_work_notes(raw: str | None) -> list[WorkNote]:
    """ServiceNow-style journal lines: '<timestamp> - <author>: <text>'. Other lines are
    continuations of the previous entry."""
    notes: list[WorkNote] = []
    for line in (raw or "").splitlines():
        match = _NOTE_RE.match(line.strip())
        if match:
            when, author, text = match.groups()
            notes.append(
                WorkNote(
                    at=datetime.fromisoformat(when), author=author, text=text, kind=_kind(text)
                )
            )
        elif notes and line.strip():
            notes[-1].text += f"\n{line.strip()}"
    return notes


def _kind(text: str) -> Literal["reassignment", "hold", "resolution", "note"]:
    if _REASSIGN_RE.match(text):
        return "reassignment"
    if "On Hold" in text:
        return "hold"
    if text.startswith("Resolved"):
        return "resolution"
    return "note"


def initial_group(notes: list[WorkNote], current: str | None) -> str | None:
    """The team the ticket was first assigned to: the first reassignment's source team."""
    for note in notes:
        match = _REASSIGN_RE.match(note.text)
        if match:
            return match.group(1)
    return current


def sla_status(row: dict[str, Any], as_of: date) -> SlaStatus:
    opened = datetime.fromisoformat(row["opened_at"])
    target = float(row["sla_target_hours"])
    if row["mttr_hours"] is not None:
        elapsed = float(row["mttr_hours"])
    elif row.get("live_elapsed_hours") is not None:
        # Live tickets run on the company's real clock, computed by the view.
        elapsed = float(row["live_elapsed_hours"])
    else:
        # The extract runs through the end of its last day.
        now = datetime.combine(as_of, time.max).replace(microsecond=0)
        elapsed = (now - opened).total_seconds() / 3600
    return SlaStatus(
        target_hours=target,
        due_at=opened + timedelta(hours=target),
        elapsed_hours=round(elapsed, 2),
        breached=bool(row["sla_breached"]),
    )


def breach_risk(row: dict[str, Any]) -> BreachRisk:
    prior = float(row.get("priority_rate") or 0.0)
    similar = int(row.get("similar_tickets") or 0)
    breaches = int(row.get("similar_breaches") or 0)
    return BreachRisk(
        similar_rate=round((breaches + RISK_SMOOTHING * prior) / (similar + RISK_SMOOTHING), 4),
        similar_tickets=similar,
        priority_rate=round(prior, 4),
        misrouted_rate=_round(row.get("misrouted_rate")),
        routed_right_rate=_round(row.get("routed_right_rate")),
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


class IncidentService:
    def __init__(self, warehouse: Warehouse, cache: TTLCache) -> None:
        self._wh = warehouse
        self._cache = cache

    def as_of(self) -> date:
        def load() -> date:
            rows = self._wh.query(AS_OF_SQL)
            if not rows or rows[0]["as_of"] is None:
                raise LookupError("no incident data")
            return date.fromisoformat(rows[0]["as_of"])

        result: date = self._cache.get_or_set(("as_of",), load)
        return result

    def list(
        self,
        status: Status = "open",
        priority: int = 0,
        assignment_group: str = "",
        breached_only: bool = False,
        q: str = "",
        limit: int = 50,
    ) -> IncidentList:
        rows = self._wh.query(
            LIST_SQL,
            {
                "status": status,
                "priority": priority,
                "assignment_group": assignment_group,
                "breached_only": int(breached_only),
                "q": q.strip(),
                "limit": limit,
            },
        )
        return IncidentList(
            as_of=self.as_of(), incidents=[IncidentRow.model_validate(r) for r in rows]
        )

    def get(self, number: str) -> IncidentDetail:
        def load() -> IncidentDetail:
            rows = self._wh.query(DETAIL_SQL, {"number": number.upper()})
            if not rows:
                raise IncidentNotFound(number)
            row = rows[0]
            risk_rows = self._wh.query(
                RISK_SQL, {"priority": row["priority"], "subcategory": row["subcategory"] or ""}
            )
            notes = parse_work_notes(row["work_notes"])
            as_of = self.as_of()
            return IncidentDetail.model_validate(
                {
                    **row,
                    "work_notes": notes,
                    "initial_group": initial_group(notes, row["assignment_group"]),
                    "sla": sla_status(row, as_of),
                    "risk": breach_risk(risk_rows[0] if risk_rows else {}),
                    "as_of": as_of,
                }
            )

        if is_live(number):
            return load()  # live tickets change as dispatchers work them
        result: IncidentDetail = self._cache.get_or_set(("detail", number.upper()), load)
        return result
