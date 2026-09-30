from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.agent.prompt import Group, Priority


class PeriodStats(BaseModel):
    opened: int
    resolved: int
    high_priority: int
    avg_mttr_hours: float | None
    sla_breach_rate: float
    reassignment_rate: float


class Overview(BaseModel):
    as_of: date
    window_days: int
    open_backlog: int
    current: PeriodStats
    previous: PeriodStats


class TrendPoint(BaseModel):
    week: date
    category: str
    incidents: int


class Trend(BaseModel):
    weeks: int
    points: list[TrendPoint]


class Hotspot(BaseModel):
    week: date
    category: str
    subcategory: str
    incidents: int
    locations: list[str]
    max_spike_ratio: float
    worst_priority: str


class GroupPerformance(BaseModel):
    assignment_group: str
    incidents: int
    avg_mttr_hours: float
    p90_mttr_hours: float
    sla_breach_rate: float
    reassignment_rate: float


class TriageRequest(BaseModel):
    short_description: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)

    def text(self) -> str:
        # Same shape as the training text: short description, newline, description.
        return "\n".join(p for p in (self.short_description.strip(), self.description.strip()) if p)


class GroupScore(BaseModel):
    assignment_group: str
    score: float


class RoutingPrediction(BaseModel):
    assignment_group: str
    confidence: float
    alternatives: list[GroupScore]
    needs_review: bool
    model_version: str


class SimilarIncident(BaseModel):
    number: str
    short_description: str | None
    close_notes: str | None
    category: str | None
    subcategory: str | None
    assignment_group: str | None
    location: str | None
    priority_label: str | None
    mttr_hours: float | None
    kb_reference: str | None
    occurrences: int
    score: float


class KbArticle(BaseModel):
    number: str
    title: str
    text: str
    kb_category: str | None
    score: float


class TriageDraft(BaseModel):
    """The agent's structured output (mirrors app.agent.prompt.DRAFT_SCHEMA)."""

    assignment_group: Group
    priority: Priority
    summary: str
    likely_cause: str
    resolution_steps: list[str]
    citations: list[str]
    routing_rationale: str
    related_to_active_spike: bool
    spike_note: str
    clarifying_questions: list[str]


class TriageFeedback(BaseModel):
    """A dispatcher's decision on an agent draft."""

    run_id: UUID
    decision: Literal["accepted", "edited", "rejected"]
    short_description: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    suggested_group: Group
    final_group: Group
    priority: Priority
    resolution: str = Field(default="", max_length=4000)
    citations: list[str] = Field(default_factory=list, max_length=20)
    agent_model: str = Field(max_length=64)


class TriageSuggestion(BaseModel):
    routing: RoutingPrediction
    similar_incidents: list[SimilarIncident]
    kb_articles: list[KbArticle]
