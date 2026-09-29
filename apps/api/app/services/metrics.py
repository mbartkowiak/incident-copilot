"""Dashboard metrics over the gold tables.

Every query is a fixed template with bound parameters; nothing user-supplied is
interpolated into SQL. The agent will reuse these same templates as tools.
"""

from app.models import GroupPerformance, Hotspot, Overview, PeriodStats, Trend, TrendPoint
from app.services.cache import TTLCache
from app.services.warehouse import Warehouse

# The dataset is a fixed extract, so "now" is the latest incident date, not the wall clock.
_AS_OF = (
    "WITH bounds AS (SELECT min(opened_date) AS first_day, max(opened_date) AS as_of "
    "FROM gold_incident_facts)"
)

OVERVIEW_SQL = f"""
{_AS_OF}
SELECT
  CASE WHEN f.opened_date > date_sub(b.as_of, :days) THEN 'current' ELSE 'previous' END AS period,
  CAST(b.as_of AS STRING) AS as_of,
  (SELECT count(*) FROM gold_incident_facts WHERE NOT is_resolved) AS open_backlog,
  count(*) AS opened,
  count_if(f.is_resolved) AS resolved,
  count_if(f.priority <= 2) AS high_priority,
  avg(f.mttr_hours) AS avg_mttr_hours,
  avg(CAST(f.sla_breached AS INT)) AS sla_breach_rate,
  avg(CAST(f.was_reassigned AS INT)) AS reassignment_rate
FROM gold_incident_facts f CROSS JOIN bounds b
WHERE f.opened_date > date_sub(b.as_of, 2 * :days)
GROUP BY 1, 2
"""

TREND_SQL = f"""
{_AS_OF}
SELECT f.opened_week AS week, f.category, count(*) AS incidents
FROM gold_incident_facts f CROSS JOIN bounds b
WHERE f.opened_week > date_sub(b.as_of, 7 * :weeks)
  -- partial weeks at either end of the extract would read as false dips
  AND f.opened_week >= b.first_day
  AND date_add(f.opened_week, 6) <= b.as_of
GROUP BY 1, 2
ORDER BY 1, 2
"""

HOTSPOTS_SQL = """
SELECT
  opened_week AS week,
  category,
  subcategory,
  CAST(sum(incidents) AS INT) AS incidents,
  array_sort(collect_set(location)) AS locations,
  max(spike_ratio) AS max_spike_ratio,
  min(worst_priority_label) AS worst_priority
FROM gold_hotspots
WHERE is_spike
GROUP BY 1, 2, 3
ORDER BY week DESC, incidents DESC
LIMIT :limit
"""

GROUPS_SQL = f"""
{_AS_OF}
SELECT
  f.assignment_group,
  count(*) AS incidents,
  avg(f.mttr_hours) AS avg_mttr_hours,
  percentile_approx(f.mttr_hours, 0.9) AS p90_mttr_hours,
  avg(CAST(f.sla_breached AS INT)) AS sla_breach_rate,
  avg(CAST(f.was_reassigned AS INT)) AS reassignment_rate
FROM gold_incident_facts f CROSS JOIN bounds b
WHERE f.is_resolved AND f.opened_date > date_sub(b.as_of, :days)
GROUP BY 1
ORDER BY incidents DESC
"""

_EMPTY = PeriodStats(
    opened=0,
    resolved=0,
    high_priority=0,
    avg_mttr_hours=None,
    sla_breach_rate=0,
    reassignment_rate=0,
)


class MetricsService:
    def __init__(self, warehouse: Warehouse, cache: TTLCache) -> None:
        self._wh = warehouse
        self._cache = cache

    def overview(self, days: int = 30) -> Overview:
        def load() -> Overview:
            rows = {r["period"]: r for r in self._wh.query(OVERVIEW_SQL, {"days": days})}
            if not rows:
                raise LookupError("no incident data")
            any_row = next(iter(rows.values()))
            return Overview(
                as_of=any_row["as_of"],
                window_days=days,
                open_backlog=any_row["open_backlog"],
                current=PeriodStats.model_validate(rows["current"])
                if "current" in rows
                else _EMPTY,
                previous=PeriodStats.model_validate(rows["previous"])
                if "previous" in rows
                else _EMPTY,
            )

        result: Overview = self._cache.get_or_set(("overview", days), load)
        return result

    def trend(self, weeks: int = 52) -> Trend:
        def load() -> Trend:
            rows = self._wh.query(TREND_SQL, {"weeks": weeks})
            return Trend(weeks=weeks, points=[TrendPoint.model_validate(r) for r in rows])

        result: Trend = self._cache.get_or_set(("trend", weeks), load)
        return result

    def hotspots(self, limit: int = 10) -> list[Hotspot]:
        def load() -> list[Hotspot]:
            rows = self._wh.query(HOTSPOTS_SQL, {"limit": limit})
            return [Hotspot.model_validate(r) for r in rows]

        result: list[Hotspot] = self._cache.get_or_set(("hotspots", limit), load)
        return result

    def groups(self, days: int = 90) -> list[GroupPerformance]:
        def load() -> list[GroupPerformance]:
            rows = self._wh.query(GROUPS_SQL, {"days": days})
            return [GroupPerformance.model_validate(r) for r in rows]

        result: list[GroupPerformance] = self._cache.get_or_set(("groups", days), load)
        return result
