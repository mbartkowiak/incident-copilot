"""Run the triage agent over the golden set and score it with deterministic checks.

    uv run python -m evals.run                 # all cases
    uv run python -m evals.run --limit 8       # quick subset

Needs Databricks auth (APP_DATABRICKS_PROFILE or DATABRICKS_* env) and ANTHROPIC_API_KEY.
Costs roughly $0.06 per case. Exits non-zero if any metric falls below its threshold.
"""

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent.runner import TriageAgent
from app.deps import get_agent, get_routing_model
from app.models import TriageRequest

HERE = Path(__file__).parent
THRESHOLDS = {
    "team_accuracy_clear": 0.90,
    "grounded_rate": 0.95,
    "expected_kb_cited_rate_clear": 0.70,
    "questions_on_vague_rate": 0.80,
    "error_rate_max": 0.05,
}


@dataclass
class CaseResult:
    id: str
    is_vague: bool
    true_group: str
    predicted_group: str | None
    team_correct: bool
    grounded: bool
    cited_expected_kb: bool
    asked_questions: bool
    error: str | None
    cost_usd: float
    latency_s: float
    turns: int


def run_case(agent: TriageAgent, case: dict[str, Any]) -> CaseResult:
    request = TriageRequest(
        short_description=case["short_description"], description=case["description"]
    )
    draft: dict[str, Any] | None = None
    grounding: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    error = None
    for event in agent.run(request):
        if event.type == "draft":
            draft, grounding = event.data["draft"], event.data["grounding"]
        elif event.type == "usage":
            usage = event.data
        elif event.type == "error":
            error = event.data["message"]
    group = draft["assignment_group"] if draft else None
    return CaseResult(
        id=case["id"],
        is_vague=case["is_vague"],
        true_group=case["true_group"],
        predicted_group=group,
        team_correct=group == case["true_group"],
        grounded=bool(draft) and not grounding.get("ungrounded"),
        cited_expected_kb=bool(draft) and case["expected_kb"] in draft["citations"],
        asked_questions=bool(draft) and len(draft["clarifying_questions"]) > 0,
        error=error if not draft else None,
        cost_usd=usage.get("cost_usd", 0.0),
        latency_s=usage.get("latency_s", 0.0),
        turns=usage.get("turns", 0),
    )


def _rate(results: list[CaseResult], attr: str) -> float | None:
    """None when the subset is empty, so a filtered run doesn't fail on what it didn't test."""
    return sum(getattr(r, attr) for r in results) / len(results) if results else None


def summarize(results: list[CaseResult]) -> dict[str, float | None]:
    clear = [r for r in results if not r.is_vague]
    vague = [r for r in results if r.is_vague]
    ok = [r for r in results if r.error is None]
    return {
        "cases": len(results),
        "team_accuracy": _rate(results, "team_correct"),
        "team_accuracy_clear": _rate(clear, "team_correct"),
        "team_accuracy_vague": _rate(vague, "team_correct"),
        "grounded_rate": _rate(ok, "grounded"),
        "expected_kb_cited_rate_clear": _rate(clear, "cited_expected_kb"),
        "questions_on_vague_rate": _rate(vague, "asked_questions"),
        "questions_on_clear_rate": _rate(clear, "asked_questions"),
        "error_rate": 1 - len(ok) / len(results) if results else 0.0,
        "mean_cost_usd": statistics.mean(r.cost_usd for r in results) if results else 0.0,
        "p50_latency_s": statistics.median(r.latency_s for r in results) if results else 0.0,
        "mean_turns": statistics.mean(r.turns for r in results) if results else 0.0,
    }


def failures(summary: dict[str, float | None]) -> list[str]:
    out = []
    for key, minimum in THRESHOLDS.items():
        if key == "error_rate_max":
            continue
        value = summary[key]
        if value is not None and value < minimum:
            out.append(f"{key} {value:.2f} < {minimum:.2f}")
    error_rate = summary["error_rate"] or 0.0
    if error_rate > THRESHOLDS["error_rate_max"]:
        out.append(f"error_rate {error_rate:.2f} > {THRESHOLDS['error_rate_max']:.2f}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    cases = [json.loads(line) for line in (HERE / "golden.jsonl").read_text().splitlines() if line]
    if args.limit:
        cases = cases[: args.limit]

    get_routing_model().load()
    agent = get_agent()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda c: run_case(agent, c), cases))

    summary = summarize(results)
    failed = failures(summary)
    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": summary,
        "thresholds": THRESHOLDS,
        "passed": not failed,
        "failures": failed,
        "cases": [asdict(r) for r in results],
    }
    out = HERE / "reports" / "latest.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for key, value in summary.items():
        shown = "n/a" if value is None else f"{value:.3f}" if isinstance(value, float) else value
        print(f"{key:32} {shown}")
    for r in results:
        if not r.team_correct or not r.grounded or r.error:
            print(f"  MISS {r.id} vague={r.is_vague} true={r.true_group} got={r.predicted_group} "
                  f"grounded={r.grounded} err={r.error}")  # fmt: skip
    print("PASS" if not failed else "FAIL: " + "; ".join(failed))
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
