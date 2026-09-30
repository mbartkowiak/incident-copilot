import time

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

INCIDENTS_SQL = """
SELECT
  number,
  opened_at,
  concat_ws('\n', short_description, description) AS text,
  assignment_group AS label,
  was_reassigned
FROM workspace.incident_copilot.gold_incident_facts
WHERE is_resolved
"""


def load_incidents(client: WorkspaceClient, warehouse_id: str) -> pd.DataFrame:
    """Resolved incidents with the final (correct) resolver group as the label."""
    api = client.statement_execution
    resp = api.execute_statement(
        statement=INCIDENTS_SQL, warehouse_id=warehouse_id, wait_timeout="30s"
    )
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(1)
        assert resp.statement_id
        resp = api.get_statement(resp.statement_id)
    if not resp.status or resp.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"query failed: {resp.status}")
    assert resp.manifest and resp.manifest.schema and resp.manifest.schema.columns
    columns = [c.name for c in resp.manifest.schema.columns]
    rows = list(resp.result.data_array or []) if resp.result else []
    for chunk in range(1, resp.manifest.total_chunk_count or 1):
        assert resp.statement_id
        rows.extend(api.get_statement_result_chunk_n(resp.statement_id, chunk).data_array or [])

    df = pd.DataFrame(rows, columns=columns)
    df["opened_at"] = pd.to_datetime(df["opened_at"], utc=True).dt.tz_convert(None)
    df["was_reassigned"] = df["was_reassigned"] == "true"
    return df.sort_values("opened_at").reset_index(drop=True)


def time_split(df: pd.DataFrame, cutoff: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on the past, test on the future, as the model would be used."""
    ts = pd.Timestamp(cutoff)
    return df[df["opened_at"] < ts].copy(), df[df["opened_at"] >= ts].copy()
