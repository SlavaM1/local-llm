from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, *, cost: int = 1, window_seconds: int = 60) -> int | None:
        now = monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) + cost > limit:
                return max(1, int(window_seconds - (now - events[0])) + 1)
            events.extend([now] * cost)
            return None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


generation_limiter = SlidingWindowRateLimiter()
login_limiter = SlidingWindowRateLimiter()
