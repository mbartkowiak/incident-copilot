from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.deps import get_metrics_service
from app.main import create_app
from app.services.cache import TTLCache
from app.services.metrics import (
    GROUPS_SQL,
    HOTSPOTS_SQL,
    OVERVIEW_SQL,
    TREND_SQL,
    MetricsService,
)
from tests.fakes import FakeWarehouse


def _period(period: str, opened: int) -> dict[str, object]:
    return {
        "period": period,
        "as_of": "2026-09-27",
        "open_backlog": 4,
        "opened": opened,
        "resolved": opened - 2,
        "high_priority": 10,
        "avg_mttr_hours": 15.5,
        "sla_breach_rate": 0.05,
        "reassignment_rate": 0.24,
    }


RESPONSES = {
    OVERVIEW_SQL: [_period("current", 646), _period("previous", 728)],
    TREND_SQL: [
        {"week": "2026-09-21", "category": "network", "incidents": 30},
        {"week": "2026-09-21", "category": "software", "incidents": 55},
    ],
    HOTSPOTS_SQL: [
        {
            "week": "2026-03-09",
            "category": "network",
            "subcategory": "lan",
            "incidents": 84,
            "locations": ["Chicago HQ"],
            "max_spike_ratio": 84.0,
            "worst_priority": "2 - High",
        }
    ],
    GROUPS_SQL: [
        {
            "assignment_group": "Network Operations",
            "incidents": 203,
            "avg_mttr_hours": 9.9,
            "p90_mttr_hours": 20.1,
            "sla_breach_rate": 0.03,
            "reassignment_rate": 0.27,
        }
    ],
}


@pytest.fixture
def warehouse() -> FakeWarehouse:
    return FakeWarehouse(RESPONSES)


@pytest.fixture
def service(warehouse: FakeWarehouse) -> MetricsService:
    return MetricsService(warehouse, TTLCache(ttl_seconds=60))


@pytest.fixture
def client(service: MetricsService) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_metrics_service] = lambda: service
    yield TestClient(app)


def test_overview_maps_both_periods(service: MetricsService) -> None:
    result = service.overview(30)

    assert result.as_of == date(2026, 9, 27)
    assert result.open_backlog == 4
    assert result.current.opened == 646
    assert result.previous.opened == 728


def test_overview_without_previous_period_is_zeroed() -> None:
    wh = FakeWarehouse({OVERVIEW_SQL: [_period("current", 10)]})
    result = MetricsService(wh, TTLCache(60)).overview(30)

    assert result.previous.opened == 0
    assert result.previous.avg_mttr_hours is None


def test_queries_are_parameterized(service: MetricsService, warehouse: FakeWarehouse) -> None:
    service.overview(45)
    service.trend(26)
    service.hotspots(5)
    service.groups(60)

    assert [params for _, params in warehouse.calls] == [
        {"days": 45},
        {"weeks": 26},
        {"limit": 5},
        {"days": 60},
    ]


def test_results_are_cached_per_parameter(
    service: MetricsService, warehouse: FakeWarehouse
) -> None:
    service.trend(52)
    service.trend(52)
    service.trend(26)

    assert len(warehouse.calls) == 2


def test_metric_endpoints_return_data(client: TestClient) -> None:
    for path in ("overview", "trend", "hotspots", "groups"):
        response = client.get(f"/api/metrics/{path}")
        assert response.status_code == 200, path

    hotspots = client.get("/api/metrics/hotspots").json()
    assert hotspots[0]["subcategory"] == "lan"
    assert hotspots[0]["locations"] == ["Chicago HQ"]


@pytest.mark.parametrize(
    "path",
    ["overview?days=1", "trend?weeks=500", "hotspots?limit=0", "groups?days=9999"],
)
def test_out_of_range_parameters_are_rejected(client: TestClient, path: str) -> None:
    assert client.get(f"/api/metrics/{path}").status_code == 422


def test_warehouse_failure_returns_503(client: TestClient, warehouse: FakeWarehouse) -> None:
    warehouse.fail = True

    response = client.get("/api/metrics/overview")

    assert response.status_code == 503
    assert response.json() == {"detail": "Data warehouse unavailable"}
