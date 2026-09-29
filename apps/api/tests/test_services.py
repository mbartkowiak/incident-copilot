import pytest
from databricks.sdk.service.sql import ColumnInfoTypeName as T

from app.services.cache import TTLCache
from app.services.warehouse import _param, convert_value


@pytest.mark.parametrize(
    ("value", "type_name", "expected"),
    [
        ("42", T.LONG, 42),
        ("0.25", T.DOUBLE, 0.25),
        ("12.50", T.DECIMAL, 12.5),
        ("true", T.BOOLEAN, True),
        ("false", T.BOOLEAN, False),
        ('["Chicago HQ","Remote"]', T.ARRAY, ["Chicago HQ", "Remote"]),
        ("2026-09-27", T.DATE, "2026-09-27"),
        (None, T.LONG, None),
    ],
)
def test_convert_value(value: str | None, type_name: T, expected: object) -> None:
    assert convert_value(value, type_name) == expected


def test_param_types() -> None:
    assert _param("n", 5).type == "INT"
    assert _param("x", 0.5).type == "DOUBLE"
    assert _param("s", "vpn").type == "STRING"
    with pytest.raises(TypeError):
        _param("b", True)


def test_ttl_cache_expires() -> None:
    now = [0.0]
    cache = TTLCache(ttl_seconds=10, clock=lambda: now[0])
    calls = []

    def compute() -> int:
        calls.append(1)
        return len(calls)

    assert cache.get_or_set("k", compute) == 1
    now[0] = 9
    assert cache.get_or_set("k", compute) == 1
    now[0] = 11
    assert cache.get_or_set("k", compute) == 2
