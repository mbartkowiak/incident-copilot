import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/quality", tags=["quality"])

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
