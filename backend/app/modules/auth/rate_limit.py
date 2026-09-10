from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.modules.auth.errors import AuthProblem


@dataclass
class Window:
    started_at: float
    count: int


class FixedWindowLimiter:
    """Bounded, process-local V1 abuse control; edge/distributed limiting remains future work."""

    def __init__(self, limit: int, window_seconds: int, max_keys: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._windows: OrderedDict[str, Window] = OrderedDict()
        self._lock = Lock()

    def check(self, key: str, *, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        with self._lock:
            self._expire(current)
            window = self._windows.get(key)
            if window is None or current - window.started_at >= self.window_seconds:
                if len(self._windows) >= self.max_keys:
                    self._windows.popitem(last=False)
                self._windows[key] = Window(current, 1)
                return
            self._windows.move_to_end(key)
            if window.count >= self.limit:
                raise AuthProblem("auth_rate_limited", 429)
            window.count += 1

    def _expire(self, now: float) -> None:
        stale = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= self.window_seconds
        ]
        for key in stale:
            self._windows.pop(key, None)

    @property
    def key_count(self) -> int:
        with self._lock:
            return len(self._windows)
