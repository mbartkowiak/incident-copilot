import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import STAFF, require

router = APIRouter(prefix="/api/quality", tags=["quality"], dependencies=[Depends(require(*STAFF))])

REPORTS = Path(__file__).resolve().parents[2] / "evals" / "reports"


@lru_cache
def _load(name: str) -> dict[str, Any] | None:
    path = REPORTS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@router.get("/agent-evals")
def agent_evals() -> dict[str, Any]:
    """The committed eval reports: the latest run and the pre-tuning baseline."""
    latest = _load("latest")
    if latest is None:
        raise HTTPException(status_code=404, detail="No eval report available")
    return {"latest": latest, "baseline": _load("baseline")}


@router.get("/feature-evals")
def feature_evals() -> dict[str, Any]:
    """Eval reports for the one-call AI features (summaries, knowledge drafts, reviews, problem
    records, attachments, intake), before and after the fixes they prompted. Model outputs are
    left out of the response; they stay in the committed reports for review."""
    latest = _load("features-latest")
    if latest is None:
        raise HTTPException(status_code=404, detail="No feature eval report available")

    def slim(report: dict[str, Any] | None) -> dict[str, Any] | None:
        if report is None:
            return None
        cases = [{k: v for k, v in c.items() if k != "output"} for c in report["cases"]]
        return {**report, "cases": cases}

    return {"latest": slim(latest), "baseline": slim(_load("features-baseline"))}
