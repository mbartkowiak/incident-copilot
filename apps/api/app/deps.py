from functools import lru_cache

from databricks.sdk import WorkspaceClient

from app.config import get_settings
from app.services.cache import TTLCache
from app.services.metrics import MetricsService
from app.services.warehouse import DatabricksWarehouse


@lru_cache
def get_metrics_service() -> MetricsService:
    settings = get_settings()
    if not settings.databricks_warehouse_id:
        raise RuntimeError("APP_DATABRICKS_WAREHOUSE_ID is not set")
    client = WorkspaceClient(profile=settings.databricks_profile)
    warehouse = DatabricksWarehouse(
        client,
        warehouse_id=settings.databricks_warehouse_id,
        catalog=settings.databricks_catalog,
        schema=settings.databricks_schema,
    )
    return MetricsService(warehouse, TTLCache(settings.metrics_cache_ttl_seconds))
