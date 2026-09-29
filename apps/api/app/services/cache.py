import threading
import time
from collections.abc import Callable, Hashable
from typing import Any


class TTLCache:
    """Tiny thread-safe cache. Gold tables change only when the pipeline runs."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > now:
                return hit[1]
        value = compute()
        with self._lock:
            self._items[key] = (now + self._ttl, value)
        return value
