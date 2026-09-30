"""Compare SLA breach-risk estimators on held-out months.

uv run python -m sla.evaluate

Breaches are almost all P1/P2 (P3-P5 targets are days long), so priority alone ranks the full
population well. The question that matters is which urgent tickets will breach, so every
estimator is also scored on P1/P2 only.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from databricks.sdk import WorkspaceClient
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from routing.data import time_split
from sla.data import load_incidents
from sla.model import breach_rate_lookup, build_pipeline, intake_features

REPORT = Path(__file__).resolve().parent.parent / "reports" / "sla_risk_eval.json"


def metrics(y: pd.Series, p: pd.Series) -> dict[str, float]:
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 3),
        "average_precision": round(float(average_precision_score(y, p)), 3),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def breach_by_routing(df: pd.DataFrame) -> dict[str, Any]:
    urgent = df[df["priority"] <= 2]
    rates = urgent.groupby("was_reassigned")["sla_breached"].agg(["mean", "size"])
    return {
        ("misrouted" if reassigned else "routed_right"): {
            "breach_rate": round(float(row["mean"]), 3),
            "tickets": int(row["size"]),
        }
        for reassigned, row in rates.iterrows()
    }


def evaluate(df: pd.DataFrame, cutoff: str) -> dict[str, Any]:
    train, test = time_split(df, cutoff)
    by_priority = train.groupby("priority")["sla_breached"].mean()
    clf = build_pipeline().fit(intake_features(train), train["sla_breached"])
    scores = pd.DataFrame(
        {
            "priority_only": test["priority"].map(by_priority).fillna(train["sla_breached"].mean()),
            "subcategory_priority_lookup": breach_rate_lookup(train, test),
            "logistic_regression": clf.predict_proba(intake_features(test))[:, 1],
        },
        index=test.index,
    )
    urgent = test["priority"] <= 2
    return {
        "cutoff": cutoff,
        "train_rows": len(train),
        "test_rows": len(test),
        "breach_rate": round(float(test["sla_breached"].mean()), 3),
        "urgent_test_rows": int(urgent.sum()),
        "urgent_breach_rate": round(float(test.loc[urgent, "sla_breached"].mean()), 3),
        "all_tickets": {c: metrics(test["sla_breached"], scores[c]) for c in scores},
        "p1_p2_only": {
            c: metrics(test.loc[urgent, "sla_breached"], scores.loc[urgent, c]) for c in scores
        },
        "p1_p2_breach_by_routing": breach_by_routing(df),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-id", default="1ace299486bf57e9")
    parser.add_argument("--cutoff", default="2026-07-01")
    args = parser.parse_args()

    results = evaluate(load_incidents(WorkspaceClient(), args.warehouse_id), args.cutoff)
    print(json.dumps(results, indent=2))
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("DATABRICKS_CONFIG_PROFILE", "mjb")
    main()
