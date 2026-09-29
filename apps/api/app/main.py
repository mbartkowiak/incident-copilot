from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings

VERSION = "0.1.0"


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Incident Intelligence Copilot API", version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION, environment=settings.environment)

    return app


app = create_app()
