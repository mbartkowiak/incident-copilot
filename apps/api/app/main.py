import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_metrics_service
from app.routes import metrics
from app.services.warehouse import WarehouseError

VERSION = "0.2.0"
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().warm_cache_on_startup:
        threading.Thread(target=_warm_cache, daemon=True).start()
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

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION, environment=settings.environment)

    app.include_router(metrics.router)
    return app


app = create_app()
