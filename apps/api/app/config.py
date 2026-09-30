from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    environment: str = "local"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Local dev authenticates with a Databricks CLI profile; deployed environments leave this
    # unset and use DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET.
    databricks_profile: str | None = None
    databricks_warehouse_id: str = ""
    databricks_catalog: str = "workspace"
    databricks_schema: str = "incident_copilot"

    metrics_cache_ttl_seconds: float = 600

    routing_model_name: str = "workspace.incident_copilot.routing_model"
    routing_model_alias: str = "champion"
    incident_index: str = "workspace.incident_copilot.incident_precedents_index"
    kb_index: str = "workspace.incident_copilot.kb_docs_index"

    # Read from ANTHROPIC_API_KEY (no APP_ prefix) so .env, the container and the SDK agree.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    agent_model: str = "claude-opus-5"
    agent_effort: str = "medium"
    agent_max_turns: int = 6
    agent_runs_per_client: int = 5
    agent_client_window_s: float = 600
    agent_runs_per_day: int = 200
    summary_model: str = "claude-opus-5-5"
    summary_effort: str = "low"
    summary_runs_per_client: int = 10
    summary_client_window_s: float = 600
    summary_runs_per_day: int = 300
    # ServiceNow connector. Off unless an instance and credentials are configured; read from
    # SERVICENOW_* (no APP_ prefix) like other third-party credentials.
    servicenow_instance: str = Field(default="", validation_alias="SERVICENOW_INSTANCE")
    servicenow_user: str = Field(default="", validation_alias="SERVICENOW_USER")
    servicenow_password: SecretStr | None = Field(
        default=None, validation_alias="SERVICENOW_PASSWORD"
    )
    servicenow_poll_seconds: float = 60
    # Serverless warehouses auto-stop; warming absorbs the ~20s cold start before users arrive.
    warm_cache_on_startup: bool = False
    load_routing_model_on_startup: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
