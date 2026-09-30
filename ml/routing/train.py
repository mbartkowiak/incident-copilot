"""Train, evaluate against human routing and Claude, and register the routing model.

uv run python -m routing.train --llm-sample 200 --register
"""

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import anthropic
import mlflow
import pandas as pd
from databricks.sdk import WorkspaceClient
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline

from routing.data import load_incidents, time_split
from routing.llm import LlmPrediction, classify, cost_per_1k
from routing.model import build_pipeline

MODEL_NAME = "workspace.incident_copilot.routing_model"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def score(y_true: pd.Series, y_pred: list[str] | pd.Series) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def single_prediction_latency(pipe: Pipeline, texts: pd.Series, n: int = 200) -> float:
    timings = []
    for text in texts.head(n):
        start = time.perf_counter()
        pipe.predict(pd.DataFrame({"text": [text]}))
        timings.append(time.perf_counter() - start)
    return statistics.median(timings)


def evaluate_llm(model: str, sample: pd.DataFrame) -> dict[str, Any]:
    client = anthropic.Anthropic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        preds: list[LlmPrediction] = list(
            pool.map(lambda t: classify(client, model, t), sample["text"])
        )
    latencies = sorted(p.latency_s for p in preds)
    return {
        **score(sample["label"], [p.label for p in preds]),
        "p50_latency_s": latencies[len(latencies) // 2],
        "p95_latency_s": latencies[int(len(latencies) * 0.95) - 1],
        "cost_per_1k_usd": cost_per_1k(model, preds),
        "unparseable": sum(p.label == "UNPARSEABLE" for p in preds),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-id", default="1ace299486bf57e9")
    parser.add_argument("--cutoff", default="2026-07-01")
    parser.add_argument("--llm-sample", type=int, default=200, help="0 skips the Claude comparison")
    parser.add_argument("--llm-models", default="claude-opus-5,claude-haiku-4-5")
    parser.add_argument("--register", action="store_true")
    parser.add_argument(
        "--experiment", default="/Users/michael.bartkowiak@gmail.com/incident-copilot-routing"
    )
    args = parser.parse_args()

    df = load_incidents(WorkspaceClient(), args.warehouse_id)
    train, test = time_split(df, args.cutoff)
    print(f"train={len(train)} test={len(test)} classes={df['label'].nunique()}")

    pipe = build_pipeline()
    pipe.fit(train[["text"]], train["label"])
    test_pred = pipe.predict(test[["text"]])

    results: dict[str, dict[str, Any]] = {
        "human_first_assignment": {
            "accuracy": float(1 - test["was_reassigned"].mean()),
            "note": "share of test incidents the service desk routed correctly on the first try",
        },
        "tfidf_logreg": {
            **score(test["label"], test_pred),
            "p50_latency_s": single_prediction_latency(pipe, test["text"]),
            "cost_per_1k_usd": 0.0,
        },
    }

    if args.llm_sample:
        sample = test.sample(n=min(args.llm_sample, len(test)), random_state=42)
        results["tfidf_logreg_on_llm_sample"] = score(
            sample["label"], pipe.predict(sample[["text"]])
        )
        for model in [m.strip() for m in args.llm_models.split(",") if m.strip()]:
            print(f"evaluating {model} on {len(sample)} incidents...")
            results[model] = evaluate_llm(model, sample)

    per_class = classification_report(test["label"], test_pred, zero_division=0)
    print(json.dumps(results, indent=2))
    print(per_class)

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "routing_eval.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(args.experiment)
    with mlflow.start_run(run_name="tfidf-logreg") as run:
        mlflow.log_params(
            {
                "cutoff": args.cutoff,
                "train_rows": len(train),
                "test_rows": len(test),
                "model": "tfidf(word1-2,char3-5)+logreg(C=4,balanced)",
            }  # fmt: skip
        )
        for name, metrics in results.items():
            for key, value in metrics.items():
                if isinstance(value, int | float):
                    mlflow.log_metric(f"{name}.{key}", value)
        mlflow.log_dict(results, "routing_eval.json")
        mlflow.log_text(per_class, "classification_report.txt")

        example = test[["text"]].head(3)
        info = mlflow.sklearn.log_model(
            pipe,
            name="model",
            signature=infer_signature(example, pipe.predict(example)),
            input_example=example,
            registered_model_name=MODEL_NAME if args.register else None,
        )
        print(f"run {run.info.run_id}")

    if args.register and info.registered_model_version:
        version = info.registered_model_version
        MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", version)
        print(f"registered {MODEL_NAME} v{version} as @champion")


if __name__ == "__main__":
    os.environ.setdefault("DATABRICKS_CONFIG_PROFILE", "mjb")
    main()
