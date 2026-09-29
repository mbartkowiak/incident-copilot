from collections.abc import Mapping

from app.services.warehouse import ParamValue, Row, WarehouseError


class FakeWarehouse:
    """Returns canned rows per SQL template and records every call."""

    def __init__(self, responses: Mapping[str, list[Row]] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, dict[str, ParamValue]]] = []
        self.fail = False

    def query(self, sql: str, params: Mapping[str, ParamValue] | None = None) -> list[Row]:
        self.calls.append((sql, dict(params or {})))
        if self.fail:
            raise WarehouseError("warehouse down")
        return self.responses.get(sql, [])
