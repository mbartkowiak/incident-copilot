# 0002: Serve the routing model in-process from the Unity Catalog registry

**Status:** Accepted, 2026-09-29

## Context
The routing classifier (TF-IDF + logistic regression) is trained, tracked in MLflow and registered in Unity Catalog as `workspace.incident_copilot.routing_model`. The API needs a prediction on every triage request. The two options were a Databricks Model Serving endpoint, or loading the model inside the API container.

## Decision
The API loads the version behind the `@champion` alias with `mlflow.sklearn.load_model` at startup (in a background thread) and predicts in-process.

- Prediction takes ~2 ms in-process, against a network round trip per call to a serving endpoint.
- A scale-to-zero serving endpoint has cold starts measured in minutes, which a portfolio demo that sits idle for days can't absorb. An always-on endpoint costs money for no latency benefit at this traffic level.
- Promotion stays a registry operation: move `@champion` to a new version and restart the service. The API logs and reports the loaded version (`/health`, and `model_version` in every prediction).
- The model is stored with **skops** (MLflow 3 default), not pickle, so loading it cannot execute arbitrary code.

## Consequences
- The API image carries scikit-learn, pandas and mlflow-skinny (~570 MB image, ~240 MB RSS); the task was raised to 1 GB.
- scikit-learn is pinned to the same version in `ml/` and `apps/api`.
- Until the model finishes loading (~30 s after a cold start), `/api/triage/suggest` returns 503 with `Retry-After`.
- If the model grows (for example a transformer) or other services need it, move to Model Serving. The `Router` interface in `app/services/routing.py` isolates that change.
