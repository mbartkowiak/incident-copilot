"""Major incidents and problem candidates, read from the tables the refresh job derives from
gold_incident_facts (pipelines/src/lifecycle.sql)."""

from typing import Any

from app.models import (
    Evidence,
    HourCount,
    IncidentRow,
    MajorIncident,
    MajorIncidentDetail,
    ProblemCandidate,
    ProblemDetail,
    WeekCount,
)
from app.services.cache import TTLCache
from app.services.warehouse import Warehouse

MI_COLUMNS = """
  mi_id,
  CAST(day AS STRING) AS day,
  subcategory,
  category,
  site,
  CAST(started_at AS STRING) AS started_at,
  CAST(restored_at AS STRING) AS restored_at,
  tickets,
  baseline_daily,
  spike_ratio,
  worst_priority,
  locations,
  resolving_groups,
  sla_breaches,
  avg_mttr_hours,
  top_fix
"""

MI_LIST_SQL = f"SELECT {MI_COLUMNS} FROM major_incidents ORDER BY day DESC"
MI_SQL = f"SELECT {MI_COLUMNS} FROM major_incidents WHERE mi_id = :id"

PROBLEM_COLUMNS = """
  problem_id,
  subcategory,
  category,
  CAST(first_week AS STRING) AS first_week,
  CAST(last_week AS STRING) AS last_week,
  weeks,
  tickets,
  baseline_weekly,
  CAST(excess_tickets AS INT) AS excess_tickets,
  hours_to_resolve,
  sla_breaches,
  locations,
  resolving_groups,
  top_fix,
  top_fix_share,
  top_fix_usual_share,
  major_incident
"""

PROBLEM_LIST_SQL = f"SELECT {PROBLEM_COLUMNS} FROM problem_candidates ORDER BY excess_tickets DESC"
PROBLEM_SQL = f"SELECT {PROBLEM_COLUMNS} FROM problem_candidates WHERE problem_id = :id"

# Member tickets, shaped like the incident queue's rows.
MEMBERS_SQL = """
SELECT
  f.number,
  CAST(f.opened_at AS STRING) AS opened_at,
  f.state,
  f.priority_label,
  f.short_description,
  f.assignment_group,
  f.subcategory,
  f.location,
  f.is_resolved,
  f.sla_breached,
  f.mttr_hours,
  f.close_notes
FROM {members} m
JOIN gold_incident_facts f ON f.number = m.number
WHERE m.{key} = :id
ORDER BY f.opened_at
LIMIT 500
"""
MI_MEMBERS_SQL = MEMBERS_SQL.format(members="major_incident_members", key="mi_id")
PROBLEM_MEMBERS_SQL = MEMBERS_SQL.format(members="problem_members", key="problem_id")

MI_TIMELINE_SQL = """
SELECT CAST(date_trunc('HOUR', f.opened_at) AS STRING) AS hour, count(*) AS opened
FROM major_incident_members m
JOIN gold_incident_facts f ON f.number = m.number
WHERE m.mi_id = :id
GROUP BY 1
ORDER BY 1
"""

# The subcategory's weekly volume from 12 weeks before the surge to 8 weeks after it (or the
# end of the data), including weeks with no tickets.
PROBLEM_WEEKLY_SQL = """
WITH weeks AS (
  SELECT explode(sequence(
    date_sub(CAST(:first_week AS DATE), 84),
    least(date_add(CAST(:last_week AS DATE), 56),
          (SELECT max(opened_week) FROM gold_incident_facts)),
    INTERVAL 7 DAY)) AS week
)
SELECT CAST(w.week AS STRING) AS week, count(f.number) AS tickets
FROM weeks w
LEFT JOIN gold_incident_facts f ON f.opened_week = w.week AND f.subcategory = :subcategory
GROUP BY w.week
ORDER BY w.week
"""


class NotFound(LookupError):
    pass


def evidence(share: float | None, usual: float | None) -> Evidence:
    """How strongly one fix explains the surge: its share during the surge against its usual
    share for this subcategory. A cause that suddenly accounts for most tickets is the
    signal a problem manager looks for."""
    if share is None or not usual:
        return "weak"
    lift = share / usual
    if lift >= 2 and share >= 0.5:
        return "strong"
    if lift >= 1.3:
        return "moderate"
    return "weak"


def problem(row: dict[str, Any]) -> ProblemCandidate:
    return ProblemCandidate.model_validate(
        {**row, "evidence": evidence(row["top_fix_share"], row["top_fix_usual_share"])}
    )


class LifecycleService:
    def __init__(self, warehouse: Warehouse, cache: TTLCache) -> None:
        self._wh = warehouse
        self._cache = cache

    def major_incidents(self) -> list[MajorIncident]:
        def load() -> list[MajorIncident]:
            return [MajorIncident.model_validate(r) for r in self._wh.query(MI_LIST_SQL)]

        result: list[MajorIncident] = self._cache.get_or_set(("major_incidents",), load)
        return result

    def major_incident(self, mi_id: str) -> MajorIncidentDetail:
        def load() -> MajorIncidentDetail:
            rows = self._wh.query(MI_SQL, {"id": mi_id})
            if not rows:
                raise NotFound(mi_id)
            params = {"id": mi_id}
            return MajorIncidentDetail(
                incident=MajorIncident.model_validate(rows[0]),
                timeline=[
                    HourCount.model_validate(r) for r in self._wh.query(MI_TIMELINE_SQL, params)
                ],
                tickets=[
                    IncidentRow.model_validate(r) for r in self._wh.query(MI_MEMBERS_SQL, params)
                ],
            )

        result: MajorIncidentDetail = self._cache.get_or_set(("major_incident", mi_id), load)
        return result

    def problems(self) -> list[ProblemCandidate]:
        def load() -> list[ProblemCandidate]:
            return [problem(r) for r in self._wh.query(PROBLEM_LIST_SQL)]

        result: list[ProblemCandidate] = self._cache.get_or_set(("problems",), load)
        return result

    def problem(self, problem_id: str) -> ProblemDetail:
        def load() -> ProblemDetail:
            rows = self._wh.query(PROBLEM_SQL, {"id": problem_id})
            if not rows:
                raise NotFound(problem_id)
            candidate = problem(rows[0])
            weekly = self._wh.query(
                PROBLEM_WEEKLY_SQL,
                {
                    "subcategory": candidate.subcategory,
                    "first_week": candidate.first_week.isoformat(),
                    "last_week": candidate.last_week.isoformat(),
                },
            )
            members = self._wh.query(PROBLEM_MEMBERS_SQL, {"id": problem_id})
            return ProblemDetail(
                problem=candidate,
                weekly=[WeekCount.model_validate(r) for r in weekly],
                tickets=[IncidentRow.model_validate(r) for r in members],
            )

        result: ProblemDetail = self._cache.get_or_set(("problem", problem_id), load)
        return result
