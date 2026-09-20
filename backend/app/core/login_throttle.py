"""Per-account brute-force protection for /auth/login.

IP-based slowapi limits alone are the wrong tool here: a whole classroom shares one campus
NAT address (so a tight per-IP limit locks out honest students), while an attacker rotating IPs
sails past it. This tracks failed attempts per *account* instead.

State is in-process — consistent with the app's single-instance realtime design (see README
"Known limitations"). A restart clears it, which only ever loosens the limit briefly.
"""
import threading
import time
from collections import deque

from app.core.config import get_settings

_lock = threading.Lock()
_failures: dict[str, deque[float]] = {}


def _window_seconds() -> float:
    return get_settings().login_failure_window_minutes * 60.0


def _prune(entries: deque[float], now: float) -> None:
    cutoff = now - _window_seconds()
    while entries and entries[0] < cutoff:
        entries.popleft()


def seconds_until_allowed(email: str) -> int:
    """0 if the account may attempt a login now, else the seconds until it may."""
    now = time.monotonic()
    with _lock:
        entries = _failures.get(email)
        if not entries:
            return 0
        _prune(entries, now)
        if not entries:
            _failures.pop(email, None)
            return 0
        if len(entries) < get_settings().login_max_failures:
            return 0
        return max(int(entries[0] + _window_seconds() - now) + 1, 1)


def record_failure(email: str) -> None:
    now = time.monotonic()
    with _lock:
        entries = _failures.setdefault(email, deque())
        _prune(entries, now)
        entries.append(now)


def record_success(email: str) -> None:
    with _lock:
        _failures.pop(email, None)


def reset() -> None:
    with _lock:
        _failures.clear()
