from functools import lru_cache

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
    # Serverless warehouses auto-stop; warming absorbs the ~20s cold start before users arrive.
    warm_cache_on_startup: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
