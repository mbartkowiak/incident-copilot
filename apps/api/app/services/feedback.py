from typing import Protocol

from app.models import TriageFeedback
from app.services.warehouse import Warehouse

INSERT_SQL = """
INSERT INTO triage_feedback (
  run_id, created_at, decision, short_description, description, suggested_group,
  final_group, priority, resolution, citations, agent_model, decided_by
) VALUES (
  :run_id, current_timestamp(), :decision, :short_description, :description, :suggested_group,
  :final_group, :priority, :resolution, :citations, :agent_model, :decided_by
)
"""


class FeedbackStore(Protocol):
    def record(self, feedback: TriageFeedback, decided_by: str) -> None: ...


class WarehouseFeedbackStore:
    """Appends dispatcher decisions to Delta. The refresh job turns approved ones into
    searchable precedents (the agent's memory)."""

    def __init__(self, warehouse: Warehouse) -> None:
        self._wh = warehouse

    def record(self, feedback: TriageFeedback, decided_by: str) -> None:
        self._wh.query(
            INSERT_SQL,
            {
                "run_id": str(feedback.run_id),
                "decision": feedback.decision,
                "short_description": feedback.short_description,
                "description": feedback.description,
                "suggested_group": feedback.suggested_group,
                "final_group": feedback.final_group,
                "priority": feedback.priority,
                "resolution": feedback.resolution,
                "citations": ",".join(feedback.citations),
                "agent_model": feedback.agent_model,
                "decided_by": decided_by,
            },
        )
