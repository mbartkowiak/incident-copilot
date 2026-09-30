"""Build the agent golden set from the synthetic data's ground truth.

    uv run python -m evals.build_golden --raw ../../data/raw

Cases come from the held-out months (the routing model never trained on them), stratified
by true team, with vague tickets over-sampled because that is where triage is hard.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

GOLDEN = Path(__file__).parent / "golden.jsonl"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=Path("../../data/raw"))
    parser.add_argument("--per-team", type=int, default=2)
    parser.add_argument("--vague", type=int, default=10)
    parser.add_argument("--cutoff", default="2026-07-01")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    manifest = json.loads((args.raw / "manifest.json").read_text(encoding="utf-8"))
    truth = {g["number"]: g for g in _read_jsonl(args.raw / "ground_truth" / "ground_truth.jsonl")}
    incidents = {
        i["number"]: i for i in _read_jsonl(args.raw / "incidents" / "incidents.jsonl")
    }  # dedupes duplicate rows

    eligible = [
        i
        for i in incidents.values()
        if i["opened_at"] >= args.cutoff
        and i["short_description"]
        and not truth[i["number"]]["defects"]
        and not truth[i["number"]]["event"]  # outage bursts are near-identical tickets
    ]
    rng = random.Random(args.seed)
    rng.shuffle(eligible)

    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    vague: list[dict[str, Any]] = []
    for inc in eligible:
        t = truth[inc["number"]]
        (vague if t["is_vague"] else by_team[t["true_assignment_group"]]).append(inc)

    chosen = [inc for team in sorted(by_team) for inc in by_team[team][: args.per_team]]
    chosen += vague[: args.vague]

    with GOLDEN.open("w", encoding="utf-8", newline="\n") as f:
        for inc in chosen:
            t = truth[inc["number"]]
            case = {
                "id": inc["number"],
                "short_description": inc["short_description"],
                "description": inc["description"],
                "true_group": t["true_assignment_group"],
                "archetype_id": t["archetype_id"],
                "expected_kb": manifest["kb_by_archetype"][t["archetype_id"]],
                "is_vague": t["is_vague"],
            }
            f.write(json.dumps(case) + "\n")
    n_vague = sum(1 for c in chosen if truth[c["number"]]["is_vague"])
    print(f"wrote {len(chosen)} cases ({n_vague} vague) to {GOLDEN}")


if __name__ == "__main__":
    main()
