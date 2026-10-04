from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import STAFF, require
from app.deps import get_metrics_service
from app.models import GroupPerformance, Hotspot, Overview, Trend
from app.services.metrics import MetricsService

router = APIRouter(prefix="/api/metrics", tags=["metrics"], dependencies=[Depends(require(*STAFF))])

Metrics = Annotated[MetricsService, Depends(get_metrics_service)]


@router.get("/overview")
def overview(svc: Metrics, days: Annotated[int, Query(ge=7, le=180)] = 30) -> Overview:
    return svc.overview(days)


@router.get("/trend")
def trend(svc: Metrics, weeks: Annotated[int, Query(ge=4, le=104)] = 52) -> Trend:
    return svc.trend(weeks)


@router.get("/hotspots")
def hotspots(svc: Metrics, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[Hotspot]:
    return svc.hotspots(limit)


@router.get("/groups")
def groups(svc: Metrics, days: Annotated[int, Query(ge=7, le=365)] = 90) -> list[GroupPerformance]:
    return svc.groups(days)
