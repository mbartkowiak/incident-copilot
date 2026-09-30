import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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


# Timestamps are the company's local wall-clock time, as in the source system, so they carry
# no timezone and the UI shows them as-is.


class IncidentRow(BaseModel):
    number: str
    opened_at: datetime
    state: str
    priority_label: str
    short_description: str | None
    assignment_group: str | None
    subcategory: str | None
    location: str | None
    is_resolved: bool
    sla_breached: bool
    mttr_hours: float | None


class IncidentList(BaseModel):
    as_of: date
    incidents: list[IncidentRow]


class WorkNote(BaseModel):
    at: datetime
    author: str
    text: str
    kind: Literal["reassignment", "hold", "resolution", "note"]


class SlaStatus(BaseModel):
    target_hours: float
    due_at: datetime
    # Resolution time for resolved tickets; time open so far (to the data's as-of) otherwise.
    elapsed_hours: float
    breached: bool


class BreachRisk(BaseModel):
    """How often tickets like this one miss their SLA, from resolved history."""

    similar_rate: float
    similar_tickets: int
    priority_rate: float
    misrouted_rate: float | None
    routed_right_rate: float | None


class IncidentDetail(BaseModel):
    number: str
    state: str
    opened_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    priority: int
    priority_label: str
    short_description: str | None
    description: str | None
    category: str | None
    subcategory: str | None
    cmdb_ci: str | None
    location: str | None
    contact_type: str | None
    assignment_group: str | None
    assigned_to: str | None
    initial_group: str | None
    reassignment_count: int
    reopen_count: int
    close_code: str | None
    close_notes: str | None
    work_notes: list[WorkNote]
    sla: SlaStatus
    risk: BreachRisk
    as_of: date


class TicketSummary(BaseModel):
    """Claude's structured summary of a ticket (mirrors app.services.summary.SUMMARY_SCHEMA)."""

    headline: str
    status: str
    actions_taken: list[str]
    next_step: str
    watch_outs: list[str]


KbAction = Literal["none", "update", "new"]
# Source KB articles, and articles created from approved drafts (see pipelines rag_sources.sql).
KB_NUMBER = r"^(KB\d{7}|KBD-[0-9a-f]{8})$"


class KbDraft(BaseModel):
    """Claude's knowledge-base proposal (mirrors app.services.knowledge.DRAFT_SCHEMA)."""

    action: KbAction
    target_kb: str
    title: str
    symptoms: str
    cause: str
    steps: list[str]
    rationale: str


class KbDraftResponse(BaseModel):
    number: str
    draft: KbDraft
    candidates: list[KbArticle]
    model: str
    cost_usd: float
    latency_s: float
    cached: bool


class KbDecision(BaseModel):
    """An engineer's decision on a knowledge draft, possibly after editing it."""

    source_number: str = Field(pattern=r"^INC\d{7}$")
    decision: Literal["approved", "rejected"]
    action: Literal["update", "new"]
    target_kb: str = Field(default="", max_length=20)
    title: str = Field(min_length=5, max_length=200)
    symptoms: str = Field(min_length=1, max_length=2000)
    cause: str = Field(min_length=1, max_length=2000)
    steps: list[str] = Field(min_length=1, max_length=15)
    model: str = Field(max_length=64)

    @model_validator(mode="after")
    def check_target(self) -> "KbDecision":
        if self.action == "update" and not re.fullmatch(KB_NUMBER, self.target_kb):
            raise ValueError("an update needs the KB number it revises")
        if self.action == "new" and self.target_kb:
            raise ValueError("a new article has no target_kb")
        if any(not s.strip() or len(s) > 500 for s in self.steps):
            raise ValueError("steps must be 1-500 characters")
        return self


class TicketSummaryResponse(BaseModel):
    number: str
    summary: TicketSummary
    model: str
    cost_usd: float
    latency_s: float
    cached: bool
