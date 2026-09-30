from datetime import date

from pydantic import BaseModel, Field


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


class TriageSuggestion(BaseModel):
    routing: RoutingPrediction
    similar_incidents: list[SimilarIncident]
    kb_articles: list[KbArticle]
