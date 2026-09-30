import logging
import threading
from typing import Any, Protocol

from app.models import GroupScore, RoutingPrediction

log = logging.getLogger(__name__)

# Below this, the UI asks a human to confirm instead of presenting the team as the answer.
REVIEW_THRESHOLD = 0.6


class ModelNotReady(RuntimeError):
    pass


class Router(Protocol):
    def predict(self, text: str) -> RoutingPrediction: ...

    def status(self) -> str: ...


def to_prediction(
    classes: list[str], probabilities: list[float], version: str
) -> RoutingPrediction:
    ranked = sorted(zip(classes, probabilities, strict=True), key=lambda p: p[1], reverse=True)
    top_group, top_score = ranked[0]
    return RoutingPrediction(
        assignment_group=top_group,
        confidence=round(top_score, 4),
        alternatives=[GroupScore(assignment_group=g, score=round(s, 4)) for g, s in ranked[1:3]],
        needs_review=top_score < REVIEW_THRESHOLD,
        model_version=version,
    )


class UcRoutingModel:
    """Champion routing model loaded from the Unity Catalog registry.

    Loaded in-process rather than behind a serving endpoint: prediction takes ~2 ms and
    avoids a network hop and scale-to-zero cold starts. Promotion is an alias change.
    """

    def __init__(self, model_name: str, alias: str) -> None:
        self._name = model_name
        self._alias = alias
        self._model: Any = None
        self._version = ""
        self._error: str | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                # Heavy imports stay off the startup path and out of unit tests.
                import mlflow
                from mlflow.tracking import MlflowClient

                mlflow.set_tracking_uri("databricks")
                mlflow.set_registry_uri("databricks-uc")
                version = MlflowClient().get_model_version_by_alias(self._name, self._alias)
                self._model = mlflow.sklearn.load_model(f"models:/{self._name}/{version.version}")
                self._version = str(version.version)
                self._error = None
                log.info("loaded routing model %s v%s", self._name, self._version)
            except Exception as e:
                self._error = str(e)
                log.exception("failed to load routing model")
                raise

    def status(self) -> str:
        if self._model is not None:
            return f"ready (v{self._version})"
        return "unavailable" if self._error else "loading"

    def predict(self, text: str) -> RoutingPrediction:
        if self._model is None:
            raise ModelNotReady("routing model is still loading")
        import pandas as pd

        proba = self._model.predict_proba(pd.DataFrame({"text": [text]}))[0]
        return to_prediction(list(self._model.classes_), [float(p) for p in proba], self._version)
