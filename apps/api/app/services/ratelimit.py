import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimited(RuntimeError):
    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class RateLimiter:
    """Sliding-window limits: per client and a global daily budget.

    The global budget is the real cost ceiling for a public demo; the per-client limit
    only keeps one visitor from using all of it. In-memory is enough for a single task.
    """

    def __init__(
        self,
        per_client: int,
        per_client_window_s: float,
        daily: int,
        clock: Callable[[], float] = time.monotonic,
        what: str = "AI triage runs",
    ) -> None:
        self._what = what
        self._per_client = per_client
        self._window = per_client_window_s
        self._daily = daily
        self._clock = clock
        self._clients: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()
        self._lock = threading.Lock()

    def check(self, client: str) -> None:
        now = self._clock()
        with self._lock:
            _trim(self._all, now - 86_400)
            if len(self._all) >= self._daily:
                raise RateLimited("The demo's daily AI budget is used up. Try again tomorrow.",
                                  int(self._all[0] + 86_400 - now) + 1)  # fmt: skip
            hits = self._clients.setdefault(client, deque())
            _trim(hits, now - self._window)
            if len(hits) >= self._per_client:
                raise RateLimited(f"Too many {self._what}. Please wait a few minutes.",
                                  int(hits[0] + self._window - now) + 1)  # fmt: skip
            hits.append(now)
            self._all.append(now)


def _trim(q: deque[float], cutoff: float) -> None:
    while q and q[0] <= cutoff:
        q.popleft()
