import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from config import settings
from utils.errors import DatasetError

MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """A sliding-window limiter kept in memory. It is right for a single server process."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float) -> float:
        """Records a request. Returns 0 if it is allowed, otherwise the seconds to wait."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= window:
                hits.popleft()
            if len(hits) >= limit:
                return window - (now - hits[0])
            hits.append(now)
            if len(self._hits) > MAX_TRACKED_KEYS:
                self._prune(now, window)
            return 0.0

    def _prune(self, now: float, window: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or now - hits[-1] >= window]
        for key in stale:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_key(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(bucket: str, per_minute: Callable[[], int]):
    """Builds a FastAPI dependency that limits requests per client address."""

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        wait = limiter.check(f"{bucket}:{client_key(request)}", per_minute(), 60.0)
        if wait > 0:
            seconds = max(1, math.ceil(wait))
            raise DatasetError(
                f"Too many requests. Please wait {seconds} second(s) and try again.",
                429,
                {"Retry-After": str(seconds)},
            )

    return dependency


limit_uploads = rate_limited("upload", lambda: settings.rate_upload_per_min)
limit_chat = rate_limited("chat", lambda: settings.rate_chat_per_min)
limit_sql = rate_limited("sql", lambda: settings.rate_chat_per_min)
limit_insights = rate_limited("insights", lambda: settings.rate_chat_per_min)
limit_reports = rate_limited("reports", lambda: settings.rate_report_per_min)