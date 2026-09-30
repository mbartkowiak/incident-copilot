"""Recent-activity lookups for the agent: is this ticket part of a wider pattern?

Like the dashboard metrics, these are fixed templates with bound parameters, and the
parameters are restricted to known values before they reach SQL.
"""

from typing import Any

from app.services.cache import TTLCache
from app.services.warehouse import Warehouse

SUBCATEGORIES = (
    "access", "authentication", "certificate", "collaboration", "email", "handheld", "how-to",
    "install", "label-printer", "lan", "laptop", "lost-device", "malware", "mobile", "password",
    "performance", "peripherals", "phishing", "printer", "replication", "sap", "sap-finance",
    "sap-workflow", "sso", "vpn", "wan", "web-app", "wireless", "wms",
)  # fmt: skip
LOCATIONS = (
    "any", "Chicago HQ", "Dallas DC", "Atlanta DC", "Memphis DC", "Toronto Office", "Remote",
)  # fmt: skip

_AS_OF = "WITH bounds AS (SELECT max(opened_date) AS as_of FROM gold_incident_facts)"

VOLUME_SQL = f"""
{_AS_OF}
SELECT
  CAST(max(b.as_of) AS STRING) AS as_of,
  count_if(f.opened_date > date_sub(b.as_of, 7)) AS last_7_days,
  count_if(f.opened_date <= date_sub(b.as_of, 7)) / 8.0 AS weekly_avg_prior_8_weeks
FROM gold_incident_facts f CROSS JOIN bounds b
WHERE f.subcategory = :subcategory
  AND (:location = 'any' OR f.location = :location)
  AND f.opened_date > date_sub(b.as_of, 63)
"""

SPIKES_SQL = """
SELECT CAST(opened_week AS STRING) AS week, location, incidents, spike_ratio
FROM gold_hotspots
WHERE is_spike AND subcategory = :subcategory AND (:location = 'any' OR location = :location)
ORDER BY opened_week DESC
LIMIT 5
"""


class InvalidFilter(ValueError):
    pass


class ActivityService:
    def __init__(self, warehouse: Warehouse, cache: TTLCache) -> None:
        self._wh = warehouse
        self._cache = cache

    def recent_activity(self, subcategory: str, location: str) -> dict[str, Any]:
        if subcategory not in SUBCATEGORIES:
            raise InvalidFilter(f"unknown subcategory {subcategory!r}")
        if location not in LOCATIONS:
            raise InvalidFilter(f"unknown location {location!r}")

        def load() -> dict[str, Any]:
            params = {"subcategory": subcategory, "location": location}
            volume = self._wh.query(VOLUME_SQL, params)
            spikes = self._wh.query(SPIKES_SQL, params)
            row = volume[0] if volume else {}
            return {
                "subcategory": subcategory,
                "location": location,
                "data_as_of": row.get("as_of"),
                "last_7_days": row.get("last_7_days", 0),
                "weekly_avg_prior_8_weeks": round(
                    float(row.get("weekly_avg_prior_8_weeks") or 0), 1
                ),
                "past_spikes": spikes,
            }

        result: dict[str, Any] = self._cache.get_or_set(("activity", subcategory, location), load)
        return result
