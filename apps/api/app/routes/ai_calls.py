import logging
from collections.abc import Callable
from typing import Any

import anthropic
from fastapi import HTTPException, Request

from app import telemetry
from app.services.cache import TTLCache
from app.services.ratelimit import RateLimiter
from app.services.structured import StructuredCallFailed

log = logging.getLogger(__name__)


def cached_ai_call[T](
    cache: TTLCache,
    key: tuple[str, str],
    limiter: RateLimiter,
    request: Request,
    event: str,
    call: Callable[[], T],
    describe: Callable[[T], dict[str, Any]],
) -> tuple[T, bool]:
    """The records behind these calls don't change, so each AI result is generated once and
    served from cache after that. Only fresh generations count against the rate limit.
    Returns (result, fresh)."""
    fresh = False

    def generate() -> T:
        nonlocal fresh
        limiter.check(request.client.host if request.client else "unknown")
        fresh = True
        try:
            result = call()
        except anthropic.APIError as e:
            log.error("%s call failed: %s", event, e)
            telemetry.emit(event, id=key[1], outcome="anthropic_error")
            raise HTTPException(503, "The AI service is unavailable right now.") from None
        except StructuredCallFailed as e:
            telemetry.emit(event, id=key[1], outcome="failed", error=str(e))
            raise HTTPException(502, "The AI returned an unusable answer. Try again.") from None
        telemetry.emit(event, id=key[1], outcome="ok", **describe(result))
        return result

    result: T = cache.get_or_set(key, generate)
    return result, fresh
