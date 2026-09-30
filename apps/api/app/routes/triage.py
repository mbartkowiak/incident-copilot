from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import get_triage_service
from app.models import TriageRequest, TriageSuggestion
from app.services.triage import TriageService

router = APIRouter(prefix="/api/triage", tags=["triage"])


@router.post("/suggest")
def suggest(
    request: TriageRequest, svc: Annotated[TriageService, Depends(get_triage_service)]
) -> TriageSuggestion:
    return svc.suggest(request)
