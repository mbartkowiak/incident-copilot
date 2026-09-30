from functools import lru_cache
from typing import cast

import anthropic
from databricks.sdk import WorkspaceClient

from app.agent.runner import MessagesClient, TriageAgent
from app.agent.tools import ToolExecutor
from app.config import get_settings
from app.services.activity import ActivityService
from app.services.cache import TTLCache
from app.services.feedback import WarehouseFeedbackStore
from app.services.incidents import IncidentService
from app.services.intake import AttachmentReader
from app.services.intake_chat import IntakeAgent
from app.services.knowledge import KbDrafter, WarehouseKbDraftStore
from app.services.lifecycle import LifecycleService
from app.services.metrics import MetricsService
from app.services.ratelimit import RateLimiter
from app.services.retrieval import VectorSearchRetriever
from app.services.reviews import LifecycleWriter
from app.services.routing import UcRoutingModel
from app.services.servicenow import ServiceNowClient
from app.services.summary import TicketSummarizer
from app.services.sync import ServiceNowConnector
from app.services.tickets import TicketService
from app.services.triage import TriageService
from app.services.warehouse import DatabricksWarehouse


class NotConfigured(RuntimeError):
    pass


@lru_cache
def get_workspace_client() -> WorkspaceClient:
    return WorkspaceClient(profile=get_settings().databricks_profile or None)


@lru_cache
def get_warehouse() -> DatabricksWarehouse:
    settings = get_settings()
    if not settings.databricks_warehouse_id:
        raise RuntimeError("APP_DATABRICKS_WAREHOUSE_ID is not set")
    return DatabricksWarehouse(
        get_workspace_client(),
        warehouse_id=settings.databricks_warehouse_id,
        catalog=settings.databricks_catalog,
        schema=settings.databricks_schema,
    )


@lru_cache
def get_metrics_service() -> MetricsService:
    return MetricsService(get_warehouse(), TTLCache(get_settings().metrics_cache_ttl_seconds))


@lru_cache
def get_retriever() -> VectorSearchRetriever:
    settings = get_settings()
    return VectorSearchRetriever(get_workspace_client(), settings.incident_index, settings.kb_index)


@lru_cache
def get_routing_model() -> UcRoutingModel:
    settings = get_settings()
    return UcRoutingModel(settings.routing_model_name, settings.routing_model_alias)


@lru_cache
def get_triage_service() -> TriageService:
    return TriageService(get_routing_model(), get_retriever())


@lru_cache
def get_messages_client() -> MessagesClient:
    settings = get_settings()
    if settings.anthropic_api_key is None:
        raise NotConfigured("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(), timeout=90.0, max_retries=2
    )
    # The SDK's overloaded create() is narrower than the Protocol's **kwargs signature.
    return cast(MessagesClient, client.beta.messages)


@lru_cache
def get_agent() -> TriageAgent:
    settings = get_settings()
    activity = ActivityService(get_warehouse(), TTLCache(settings.metrics_cache_ttl_seconds))
    executor = ToolExecutor(get_routing_model(), get_retriever(), activity)
    return TriageAgent(
        get_messages_client(),
        executor,
        model=settings.agent_model,
        effort=settings.agent_effort,
        max_turns=settings.agent_max_turns,
    )


@lru_cache
def get_incident_service() -> IncidentService:
    return IncidentService(
        get_warehouse(),
        TTLCache(get_settings().metrics_cache_ttl_seconds),
        servicenow_instance=get_settings().servicenow_instance,
    )


@lru_cache
def get_summarizer() -> TicketSummarizer:
    settings = get_settings()
    return TicketSummarizer(
        get_messages_client(), model=settings.summary_model, effort=settings.summary_effort
    )


@lru_cache
def get_kb_drafter() -> KbDrafter:
    settings = get_settings()
    return KbDrafter(
        get_messages_client(),
        get_retriever(),
        model=settings.summary_model,
        effort=settings.summary_effort,
    )


@lru_cache
def get_kb_draft_store() -> WarehouseKbDraftStore:
    return WarehouseKbDraftStore(get_warehouse())


@lru_cache
def get_kb_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        per_client=settings.summary_runs_per_client,
        per_client_window_s=settings.summary_client_window_s,
        daily=settings.summary_runs_per_day,
        what="AI knowledge drafts",
    )


@lru_cache
def get_lifecycle_service() -> LifecycleService:
    return LifecycleService(get_warehouse(), TTLCache(get_settings().metrics_cache_ttl_seconds))


@lru_cache
def get_lifecycle_writer() -> LifecycleWriter:
    settings = get_settings()
    return LifecycleWriter(
        get_messages_client(), model=settings.summary_model, effort=settings.summary_effort
    )


@lru_cache
def get_review_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        per_client=settings.summary_runs_per_client,
        per_client_window_s=settings.summary_client_window_s,
        daily=settings.summary_runs_per_day,
        what="AI reviews",
    )


@lru_cache
def get_attachment_reader() -> AttachmentReader:
    settings = get_settings()
    return AttachmentReader(
        get_messages_client(), model=settings.summary_model, effort=settings.summary_effort
    )


@lru_cache
def get_attachment_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        per_client=settings.summary_runs_per_client,
        per_client_window_s=settings.summary_client_window_s,
        daily=settings.summary_runs_per_day,
        what="attachment reads",
    )


@lru_cache
def get_servicenow_connector() -> ServiceNowConnector | None:
    """The ServiceNow connector, or None when no instance is configured."""
    settings = get_settings()
    password = (
        settings.servicenow_password.get_secret_value() if settings.servicenow_password else ""
    )
    if not (settings.servicenow_instance and settings.servicenow_user and password):
        return None
    client = ServiceNowClient(settings.servicenow_instance, settings.servicenow_user, password)
    return ServiceNowConnector(client)


@lru_cache
def get_ticket_service() -> TicketService:
    connector = get_servicenow_connector()
    svc = TicketService(get_warehouse(), get_routing_model(), get_retriever(), mirror=connector)
    if connector is not None:
        connector.tickets = svc
    return svc


@lru_cache
def get_ticket_rate_limiter() -> RateLimiter:
    return RateLimiter(per_client=30, per_client_window_s=600, daily=1000, what="ticket updates")


@lru_cache
def get_intake_agent() -> IntakeAgent:
    settings = get_settings()
    return IntakeAgent(
        get_messages_client(), model=settings.summary_model, effort=settings.summary_effort
    )


@lru_cache
def get_intake_rate_limiter() -> RateLimiter:
    # Each chat turn is one small call (~1 cent); a conversation is 1-3 turns.
    return RateLimiter(per_client=20, per_client_window_s=600, daily=400, what="chat messages")


@lru_cache
def get_summary_cache() -> TTLCache:
    return TTLCache(ttl_seconds=86_400)


@lru_cache
def get_summary_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        per_client=settings.summary_runs_per_client,
        per_client_window_s=settings.summary_client_window_s,
        daily=settings.summary_runs_per_day,
        what="AI summaries",
    )


@lru_cache
def get_feedback_store() -> WarehouseFeedbackStore:
    return WarehouseFeedbackStore(get_warehouse())


@lru_cache
def get_feedback_rate_limiter() -> RateLimiter:
    return RateLimiter(per_client=20, per_client_window_s=600, daily=1000)


@lru_cache
def get_agent_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        per_client=settings.agent_runs_per_client,
        per_client_window_s=settings.agent_client_window_s,
        daily=settings.agent_runs_per_day,
    )
