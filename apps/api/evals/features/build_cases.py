"""Snapshot the inputs of the one-call AI features into evals/features/cases.json.

    uv run python -m evals.features.build_cases --raw ../../data/raw

Reads the lakehouse and the KB vector index once, so eval runs need only the Claude API key:
they are reproducible (same inputs every run) and could run in CI. Rebuild when the data
changes. Tickets come from the held-out months and are picked to cover what the prompts must
handle: SLA breaches, misroutes, reopens, open and resolved tickets, every ticket type.
"""

import argparse
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.deps import get_incident_service, get_lifecycle_service, get_retriever
from app.models import IncidentDetail
from app.services.knowledge import CANDIDATES, search_text
from app.services.reviews import sample

CASES = Path(__file__).parent / "cases.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _pick_summaries(details: list[IncidentDetail], rng: random.Random) -> list[IncidentDetail]:
    """Two of each situation a summary must recognize, without repeating a ticket."""
    situations: list[Callable[[IncidentDetail], bool]] = [
        lambda t: t.resolved_at is None,
        lambda t: t.resolved_at is not None and t.sla.breached,
        lambda t: t.reassignment_count > 0,
        lambda t: t.reopen_count > 0,
        lambda t: (
            t.resolved_at is not None
            and not t.sla.breached
            and t.reassignment_count == 0
            and t.reopen_count == 0
        ),
    ]
    chosen: dict[str, IncidentDetail] = {}
    for test in situations:
        pool = [t for t in details if test(t) and t.number not in chosen]
        for t in rng.sample(pool, min(2, len(pool))):
            chosen[t.number] = t
    return list(chosen.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=Path("../../data/raw"))
    parser.add_argument("--cutoff", default="2026-07-01")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--kb-cases", type=int, default=10)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    manifest = json.loads((args.raw / "manifest.json").read_text(encoding="utf-8"))
    truth = {g["number"]: g for g in _read_jsonl(args.raw / "ground_truth" / "ground_truth.jsonl")}

    incidents = get_incident_service()
    rows = [
        *incidents.list("open", limit=200).incidents,
        *incidents.list("resolved", breached_only=True, limit=200).incidents,
        *incidents.list("resolved", limit=200).incidents,
    ]
    numbers = sorted(
        {
            r.number
            for r in rows
            if r.number in truth
            and r.opened_at.isoformat() >= args.cutoff
            and not truth[r.number]["event"]  # outage bursts belong to the review cases
        }
    )
    details = [incidents.get(n) for n in numbers]
    summaries = _pick_summaries(details, rng)

    # One resolved ticket per ticket type, so the drafter sees every kind of fix.
    by_type: dict[str, IncidentDetail] = {}
    for t in rng.sample(details, len(details)):
        archetype = truth[t.number]["archetype_id"]
        if t.resolved_at and t.close_notes and archetype not in by_type:
            by_type[archetype] = t
    retriever = get_retriever()
    kb = [
        {
            "ticket": t.model_dump(mode="json"),
            "candidates": [
                c.model_dump(mode="json") for c in retriever.kb_articles(search_text(t), CANDIDATES)
            ],
            "expected_kb": manifest["kb_by_archetype"][archetype],
        }
        for archetype, t in sorted(by_type.items())[: args.kb_cases]
    ]

    lifecycle = get_lifecycle_service()
    # The prompts use an evenly spaced sample of tickets; keeping only that sample leaves the
    # prompts unchanged and the file small.
    reviews = [lifecycle.major_incident(m.mi_id) for m in lifecycle.major_incidents()]
    problems = [lifecycle.problem(p.problem_id) for p in lifecycle.problems()]
    for review in reviews:
        review.tickets = sample(review.tickets)
    for problem in problems:
        problem.tickets = sample(problem.tickets)

    cases = {
        "summaries": [t.model_dump(mode="json") for t in summaries],
        "kb_drafts": kb,
        "reviews": [r.model_dump(mode="json") for r in reviews],
        "problems": [p.model_dump(mode="json") for p in problems],
    }
    CASES.write_text(json.dumps(cases, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(
        f"wrote {len(summaries)} summaries, {len(kb)} knowledge drafts, {len(reviews)} reviews "
        f"and {len(problems)} problem records to {CASES}"
    )


if __name__ == "__main__":
    main()
