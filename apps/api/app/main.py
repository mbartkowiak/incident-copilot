import contextlib
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from databricks.sdk.errors.base import DatabricksError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.deps import NotConfigured, get_metrics_service, get_routing_model
from app.routes import agent, incidents, knowledge, lifecycle, metrics, quality, tickets, triage
from app.services.ratelimit import RateLimited
from app.services.routing import ModelNotReady
from app.services.warehouse import WarehouseError

VERSION = "0.6.0"
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    routing_model: str


def _warm_cache() -> None:
    try:
        svc = get_metrics_service()
        svc.overview()
        svc.trend()
        svc.hotspots()
        svc.groups()
        log.info("metrics cache warmed")
    except Exception:
        log.exception("cache warm-up failed; requests will load lazily")


def _load_routing_model() -> None:
    # Failures are logged by the model and surfaced as "unavailable" in /health.
    with contextlib.suppress(Exception):
        get_routing_model().load()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.warm_cache_on_startup:
        threading.Thread(target=_warm_cache, daemon=True).start()
    if settings.load_routing_model_on_startup:
        threading.Thread(target=_load_routing_model, daemon=True).start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Incident Intelligence Copilot API", version=VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(WarehouseError)
    async def warehouse_unavailable(_: Request, exc: WarehouseError) -> JSONResponse:
        log.error("warehouse query failed: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "Data warehouse unavailable"})

    @app.exception_handler(ModelNotReady)
    async def model_not_ready(_: Request, exc: ModelNotReady) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Routing model is still loading, try again shortly"},
            headers={"Retry-After": "10"},
        )

    @app.exception_handler(RateLimited)
    async def rate_limited(_: Request, exc: RateLimited) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": str(exc)},
            headers={"Retry-After": str(exc.retry_after_s)},
        )

    @app.exception_handler(NotConfigured)
    async def not_configured(_: Request, exc: NotConfigured) -> JSONResponse:
        log.error("service not configured: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "AI triage is not configured"})

    @app.exception_handler(DatabricksError)
    async def databricks_unavailable(_: Request, exc: DatabricksError) -> JSONResponse:
        log.error("databricks call failed: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "Search service unavailable"})

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=VERSION,
            environment=settings.environment,
            routing_model=get_routing_model().status(),
        )

    app.include_router(metrics.router)
    app.include_router(triage.router)
    app.include_router(agent.router)
    app.include_router(quality.router)
    app.include_router(incidents.router)
    app.include_router(knowledge.router)
    app.include_router(lifecycle.router)
    app.include_router(tickets.router)
    return app


app = create_app()
