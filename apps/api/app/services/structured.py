"""A single Claude request constrained to a JSON schema, for tasks that need no tools."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agent.runner import MessagesClient, Usage

log = logging.getLogger(__name__)


class StructuredCallFailed(RuntimeError):
    pass


@dataclass
class StructuredResult[T: BaseModel]:
    value: T
    model: str
    cost_usd: float
    latency_s: float
    usage: Usage


def call_structured[T: BaseModel](
    messages: MessagesClient,
    *,
    model: str,
    effort: str,
    system: str,
    schema: dict[str, Any],
    prompt: str | list[dict[str, Any]],
    output: type[T],
) -> StructuredResult[T]:
    """`prompt` is the user turn: text, or content blocks when it carries images or PDFs."""
    started = time.perf_counter()
    response = messages.create(
        model=model,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    usage = Usage()
    usage.add(response.usage)
    if response.stop_reason != "end_turn":
        raise StructuredCallFailed(f"stopped with {response.stop_reason}")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        value = output.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as e:
        log.error("invalid %s: %s", output.__name__, text[:500])
        raise StructuredCallFailed(f"invalid {output.__name__}") from e
    return StructuredResult(
        value=value,
        model=model,
        cost_usd=round(usage.cost_usd(model), 4),
        latency_s=round(time.perf_counter() - started, 2),
        usage=usage,
    )
