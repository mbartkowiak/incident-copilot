"""The agent's tools. Every tool is read-only and wraps an existing, tested service."""

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.services.activity import LOCATIONS, SUBCATEGORIES, ActivityService, InvalidFilter
from app.services.retrieval import Retriever
from app.services.routing import Router

TOOLS: list[dict[str, Any]] = [
    {
        "name": "predict_team",
        "description": "Predict the resolving team with the trained routing model. Returns the top team, its probability, and the next two alternatives.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"ticket_text": {"type": "string"}},
            "required": ["ticket_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_similar_incidents",
        "description": "Semantic search over resolved incident precedents. Each result has the example incident number, how it was fixed, the resolving team, how often it has occurred, and a similarity score (0-1).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "enum": [3, 5, 8]},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_knowledge_base",
        "description": "Semantic search over published knowledge articles. Returns article number, title, full text (symptoms, cause, resolution steps) and a similarity score.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "enum": [2, 3, 5]},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_recent_activity",
        "description": "Incident volume for one subcategory (optionally one site) in the last 7 days against the prior 8-week weekly average, plus past detected spikes with dates. Use it to tell whether a ticket belongs to a wider outage.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "subcategory": {"type": "string", "enum": list(SUBCATEGORIES)},
                "location": {"type": "string", "enum": list(LOCATIONS)},
            },
            "required": ["subcategory", "location"],
            "additionalProperties": False,
        },
    },
]  # fmt: skip


class ToolError(RuntimeError):
    pass


class _TicketText(BaseModel):
    ticket_text: str = Field(min_length=1, max_length=5000)


class _Search(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(ge=1, le=8)


class _Activity(BaseModel):
    subcategory: str
    location: str


@dataclass
class ToolOutput:
    summary: str  # one line for the UI timeline
    data: Any  # structured result for the UI and the model


@dataclass
class RunContext:
    """What the agent actually retrieved, for checking its citations afterwards."""

    retrieved_ids: set[str] = field(default_factory=set)


class ToolExecutor:
    def __init__(self, router: Router, retriever: Retriever, activity: ActivityService) -> None:
        self._router = router
        self._retriever = retriever
        self._activity = activity

    def run(self, name: str, raw_input: Any, ctx: RunContext) -> ToolOutput:
        try:
            if name == "predict_team":
                args = _TicketText.model_validate(raw_input)
                p = self._router.predict(args.ticket_text)
                alts = ", ".join(f"{a.assignment_group} {a.score:.0%}" for a in p.alternatives)
                return ToolOutput(
                    f"{p.assignment_group} ({p.confidence:.0%}); also {alts}", p.model_dump()
                )
            if name == "search_similar_incidents":
                s = _Search.model_validate(raw_input)
                hits = self._retriever.similar_incidents(s.query, s.limit)
                ctx.retrieved_ids.update(h.number for h in hits)
                # A precedent's KB reference was shown to the agent, so citing it is grounded.
                ctx.retrieved_ids.update(h.kb_reference for h in hits if h.kb_reference)
                return ToolOutput(
                    f"{len(hits)} precedents, best match {hits[0].score:.0%}"
                    if hits
                    else "no matches",
                    [h.model_dump() for h in hits],
                )
            if name == "search_knowledge_base":
                s = _Search.model_validate(raw_input)
                articles = self._retriever.kb_articles(s.query, s.limit)
                ctx.retrieved_ids.update(a.number for a in articles)
                return ToolOutput(
                    ", ".join(f"{a.number} {a.score:.0%}" for a in articles) or "no articles",
                    [a.model_dump() for a in articles],
                )
            if name == "check_recent_activity":
                a = _Activity.model_validate(raw_input)
                result = self._activity.recent_activity(a.subcategory, a.location)
                spikes = len(result["past_spikes"])
                return ToolOutput(
                    f"{result['last_7_days']} in last 7 days vs {result['weekly_avg_prior_8_weeks']}/wk"
                    f" before; {spikes} past spike(s)",
                    result,
                )
        except (ValidationError, InvalidFilter) as e:
            raise ToolError(f"invalid input for {name}: {e}") from e
        raise ToolError(f"unknown tool {name!r}")


def to_model_content(output: ToolOutput) -> str:
    return json.dumps(output.data, default=str)
