from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.auth import STAFF, require
from app.deps import (
    get_lifecycle_service,
    get_lifecycle_writer,
    get_review_rate_limiter,
    get_summary_cache,
)
from app.models import (
    AiDocument,
    IncidentReview,
    MajorIncident,
    MajorIncidentDetail,
    ProblemCandidate,
    ProblemDetail,
    ProblemRecord,
)
from app.routes.ai_calls import cached_ai_call
from app.services.cache import TTLCache
from app.services.lifecycle import LifecycleService, NotFound
from app.services.ratelimit import RateLimiter
from app.services.reviews import LifecycleWriter

router = APIRouter(prefix="/api", tags=["lifecycle"], dependencies=[Depends(require(*STAFF))])

Lifecycle = Annotated[LifecycleService, Depends(get_lifecycle_service)]
Writer = Annotated[LifecycleWriter, Depends(get_lifecycle_writer)]
Limiter = Annotated[RateLimiter, Depends(get_review_rate_limiter)]
Cache = Annotated[TTLCache, Depends(get_summary_cache)]
MiId = Annotated[str, Path(pattern=r"^MI\d{8}-[a-z-]{2,30}$")]
ProblemId = Annotated[str, Path(pattern=r"^PRB\d{8}-[a-z-]{2,30}$")]


@router.get("/major-incidents")
def list_major_incidents(svc: Lifecycle) -> list[MajorIncident]:
    return svc.major_incidents()


@router.get("/major-incidents/{mi_id}")
def get_major_incident(svc: Lifecycle, mi_id: MiId) -> MajorIncidentDetail:
    try:
        return svc.major_incident(mi_id)
    except NotFound:
        raise HTTPException(404, f"{mi_id} not found") from None


@router.post("/major-incidents/{mi_id}/review")
def review_major_incident(
    mi_id: MiId, request: Request, svc: Lifecycle, writer: Writer, limiter: Limiter, cache: Cache
) -> AiDocument[IncidentReview]:
    """Claude's post-incident review draft."""
    detail = get_major_incident(svc, mi_id)
    result, fresh = cached_ai_call(
        cache,
        ("review", mi_id),
        limiter,
        request,
        "incident_review",
        lambda: writer.review(detail),
        lambda r: {"model": r.model, "latency_s": r.latency_s, "cost_usd": r.cost_usd},
    )
    return AiDocument[IncidentReview](
        id=mi_id,
        document=result.value,
        model=result.model,
        cost_usd=result.cost_usd,
        latency_s=result.latency_s,
        cached=not fresh,
    )


@router.get("/problems")
def list_problems(svc: Lifecycle) -> list[ProblemCandidate]:
    return svc.problems()


@router.get("/problems/{problem_id}")
def get_problem(svc: Lifecycle, problem_id: ProblemId) -> ProblemDetail:
    try:
        return svc.problem(problem_id)
    except NotFound:
        raise HTTPException(404, f"{problem_id} not found") from None


@router.post("/problems/{problem_id}/record")
def draft_problem_record(
    problem_id: ProblemId,
    request: Request,
    svc: Lifecycle,
    writer: Writer,
    limiter: Limiter,
    cache: Cache,
) -> AiDocument[ProblemRecord]:
    """Claude's problem record draft: statement, root-cause hypothesis, evidence, fix."""
    detail = get_problem(svc, problem_id)
    result, fresh = cached_ai_call(
        cache,
        ("problem_record", problem_id),
        limiter,
        request,
        "problem_record",
        lambda: writer.problem_record(detail),
        lambda r: {"model": r.model, "latency_s": r.latency_s, "cost_usd": r.cost_usd},
    )
    return AiDocument[ProblemRecord](
        id=problem_id,
        document=result.value,
        model=result.model,
        cost_usd=result.cost_usd,
        latency_s=result.latency_s,
        cached=not fresh,
    )
