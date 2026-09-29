import json
import time
from collections.abc import Mapping
from typing import Any, Protocol

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import (
    ColumnInfoTypeName,
    StatementParameterListItem,
    StatementResponse,
    StatementState,
)

ParamValue = str | int | float
Row = dict[str, Any]


class WarehouseError(RuntimeError):
    pass


class Warehouse(Protocol):
    def query(self, sql: str, params: Mapping[str, ParamValue] | None = None) -> list[Row]: ...


_INTS = {ColumnInfoTypeName.BYTE, ColumnInfoTypeName.SHORT, ColumnInfoTypeName.INT,
         ColumnInfoTypeName.LONG}  # fmt: skip
_FLOATS = {ColumnInfoTypeName.FLOAT, ColumnInfoTypeName.DOUBLE, ColumnInfoTypeName.DECIMAL}
_JSON = {ColumnInfoTypeName.ARRAY, ColumnInfoTypeName.MAP, ColumnInfoTypeName.STRUCT}


def convert_value(value: str | None, type_name: ColumnInfoTypeName | None) -> Any:
    """The statement API returns every value as a string; restore Python types."""
    if value is None:
        return None
    if type_name in _INTS:
        return int(value)
    if type_name in _FLOATS:
        return float(value)
    if type_name == ColumnInfoTypeName.BOOLEAN:
        return value.lower() == "true"
    if type_name in _JSON:
        return json.loads(value)
    return value


def _param(name: str, value: ParamValue) -> StatementParameterListItem:
    if isinstance(value, bool):
        raise TypeError("boolean query parameters are not supported")
    kind = "INT" if isinstance(value, int) else "DOUBLE" if isinstance(value, float) else "STRING"
    return StatementParameterListItem(name=name, value=str(value), type=kind)


class DatabricksWarehouse:
    """Runs parameterized SQL on a Databricks SQL warehouse via the Statement Execution API."""

    def __init__(
        self,
        client: WorkspaceClient,
        warehouse_id: str,
        catalog: str,
        schema: str,
        timeout_seconds: float = 120,
    ) -> None:
        self._client = client
        self._warehouse_id = warehouse_id
        self._catalog = catalog
        self._schema = schema
        self._timeout = timeout_seconds

    def query(self, sql: str, params: Mapping[str, ParamValue] | None = None) -> list[Row]:
        api = self._client.statement_execution
        resp = api.execute_statement(
            statement=sql,
            warehouse_id=self._warehouse_id,
            catalog=self._catalog,
            schema=self._schema,
            parameters=[_param(k, v) for k, v in (params or {}).items()],
            wait_timeout="30s",
        )
        resp = self._wait(resp)
        return self._rows(resp)

    def _wait(self, resp: StatementResponse) -> StatementResponse:
        # A serverless warehouse that has auto-stopped can take a while to start.
        deadline = time.monotonic() + self._timeout
        while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
            if time.monotonic() > deadline:
                if resp.statement_id:
                    self._client.statement_execution.cancel_execution(resp.statement_id)
                raise WarehouseError("query timed out")
            time.sleep(1)
            assert resp.statement_id
            resp = self._client.statement_execution.get_statement(resp.statement_id)
        state = resp.status.state if resp.status else None
        if state != StatementState.SUCCEEDED:
            message = resp.status.error.message if resp.status and resp.status.error else None
            raise WarehouseError(f"query {state}: {message}")
        return resp

    def _rows(self, resp: StatementResponse) -> list[Row]:
        manifest = resp.manifest
        if not manifest or not manifest.schema or not manifest.schema.columns:
            return []
        columns = [
            (c.name or f"col{i}", c.type_name) for i, c in enumerate(manifest.schema.columns)
        ]
        data = list(resp.result.data_array or []) if resp.result else []
        for chunk in range(1, manifest.total_chunk_count or 1):
            assert resp.statement_id
            part = self._client.statement_execution.get_statement_result_chunk_n(
                resp.statement_id, chunk
            )
            data.extend(part.data_array or [])
        return [
            {name: convert_value(v, t) for (name, t), v in zip(columns, row, strict=True)}
            for row in data
        ]
