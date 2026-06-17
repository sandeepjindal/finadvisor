"""Per-user rate limiting and a simple daily token budget. Clock is injectable for tests.
Split from guards (Step 2.5).
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        max_calls: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_calls = max_calls
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[object, list[float]] = defaultdict(list)

    def allow(self, key: object) -> bool:
        now = self.clock()
        hits = [t for t in self._hits[key] if now - t < self.window]
        if len(hits) >= self.max_calls:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


class TokenBudget:
    def __init__(self, daily_limit: int | None):
        self.daily_limit = daily_limit
        self.used = 0

    def add(self, tokens: int) -> None:
        self.used += max(0, tokens)

    def remaining(self) -> float:
        if self.daily_limit is None:
            return float("inf")
        return max(0, self.daily_limit - self.used)

    def over(self) -> bool:
        return self.daily_limit is not None and self.used >= self.daily_limit
