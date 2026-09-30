import pandas as pd
from databricks.sdk import WorkspaceClient

from routing.data import query

INCIDENTS_SQL = """
SELECT
  number,
  opened_at,
  short_description,
  description,
  priority,
  category,
  subcategory,
  location,
  contact_type,
  was_reassigned,
  sla_breached
FROM workspace.incident_copilot.gold_incident_facts
WHERE is_resolved
"""


def load_incidents(client: WorkspaceClient, warehouse_id: str) -> pd.DataFrame:
    """Resolved incidents with their SLA outcome."""
    df = query(client, warehouse_id, INCIDENTS_SQL)
    df["opened_at"] = pd.to_datetime(df["opened_at"], utc=True).dt.tz_convert(None)
    df["priority"] = df["priority"].astype(int)
    for col in ("was_reassigned", "sla_breached"):
        df[col] = df[col] == "true"
    return df.sort_values("opened_at").reset_index(drop=True)
