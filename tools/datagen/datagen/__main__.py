import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from datagen.generator import generate


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic ITSM data.")
    parser.add_argument("--out", type=Path, default=Path("../../data/raw"))
    parser.add_argument("--count", type=int, default=8000, help="baseline incidents (bursts extra)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 10, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 27))
    args = parser.parse_args()

    ds = generate(count=args.count, seed=args.seed, start=args.start, end=args.end)

    out: Path = args.out
    _write_jsonl(out / "incidents" / "incidents.jsonl", ds.incidents)
    _write_jsonl(out / "kb_articles" / "kb_articles.jsonl", ds.kb_articles)
    # Ground truth lives outside the ingest folders: it is for evals, never for the pipeline.
    _write_jsonl(out / "ground_truth" / "ground_truth.jsonl", ds.ground_truth)
    (out / "manifest.json").write_text(json.dumps(ds.manifest, indent=2), encoding="utf-8")

    defects = Counter(d for g in ds.ground_truth for d in g["defects"])
    groups = Counter(g["true_assignment_group"] for g in ds.ground_truth)
    misrouted = sum(
        g["initial_assignment_group"] != g["true_assignment_group"] for g in ds.ground_truth
    )
    print(
        f"Wrote {len(ds.incidents)} incident rows ({len(ds.ground_truth)} unique), "
        f"{len(ds.kb_articles)} KB articles to {out.resolve()}"
    )
    print(f"Misrouted initially: {misrouted / len(ds.ground_truth):.1%}")
    print(f"Defects: {dict(defects)}")
    print("By group: " + ", ".join(f"{g}={n}" for g, n in groups.most_common()))


if __name__ == "__main__":
    main()
