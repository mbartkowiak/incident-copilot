from functools import lru_cache

from databricks.sdk import WorkspaceClient

from app.config import get_settings
from app.services.cache import TTLCache
from app.services.metrics import MetricsService
from app.services.retrieval import VectorSearchRetriever
from app.services.routing import UcRoutingModel
from app.services.triage import TriageService
from app.services.warehouse import DatabricksWarehouse


@lru_cache
def get_workspace_client() -> WorkspaceClient:
    return WorkspaceClient(profile=get_settings().databricks_profile or None)


@lru_cache
def get_metrics_service() -> MetricsService:
    settings = get_settings()
    if not settings.databricks_warehouse_id:
        raise RuntimeError("APP_DATABRICKS_WAREHOUSE_ID is not set")
    warehouse = DatabricksWarehouse(
        get_workspace_client(),
        warehouse_id=settings.databricks_warehouse_id,
        catalog=settings.databricks_catalog,
        schema=settings.databricks_schema,
    )
    return MetricsService(warehouse, TTLCache(settings.metrics_cache_ttl_seconds))


@lru_cache
def get_routing_model() -> UcRoutingModel:
    settings = get_settings()
    return UcRoutingModel(settings.routing_model_name, settings.routing_model_alias)


@lru_cache
def get_triage_service() -> TriageService:
    settings = get_settings()
    retriever = VectorSearchRetriever(
        get_workspace_client(), settings.incident_index, settings.kb_index
    )
    return TriageService(get_routing_model(), retriever)
