"""In-memory request limits per client address (DECISIONS.md D-035).

The server runs one worker, so process memory is the whole picture. Both limiters prune idle
keys and cap how many they track; past the cap, new addresses share one bucket instead of
growing the table (closed, not open).
"""

import ipaddress
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.types import Scope

MAX_TRACKED_KEYS = 20_000
OVERFLOW_KEY = "*overflow*"
# Idle keys are dropped this often, and at once when the table is full.
PRUNE_EVERY_SECONDS = 60.0


def client_ip(scope: Scope, header: str = "") -> str:
    """The client's address. A forwarding header is believed only when the operator named
    one (AM_CLIENT_IP_HEADER, e.g. CF-Connecting-IP behind Cloudflare Tunnel); otherwise,
    and when that header is missing or not an address, the socket peer is used. For a
    comma-separated list the last entry counts: it is the one the nearest proxy appended.
    """
    if header:
        raw = Headers(scope=scope).get(header.lower(), "")
        candidate = raw.rsplit(",", 1)[-1].strip()
        if candidate:
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def rate_key(ip: str) -> str:
    """One key per IPv4 address or per IPv6 /64 (a single subscriber owns the whole /64)."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network((address, 64), strict=False).network_address) + "/64"
    return str(address)


class TokenBucketLimiter:
    """`per_minute` requests a minute per key, with a burst of the same size (a page load
    fires a dozen calls at once)."""

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        if per_minute <= 0:
            raise ValueError("per_minute must be positive")
        self.capacity = float(per_minute)
        self.refill_per_second = per_minute / 60.0
        self.max_keys = max_keys
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, updated)
        self._pruned_at = clock()
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """Take one token. Returns 0.0 when allowed, else the seconds until one is back."""
        with self._lock:
            now = self._clock()
            if now - self._pruned_at >= PRUNE_EVERY_SECONDS:
                self._prune(now)
            if key not in self._buckets and len(self._buckets) >= self.max_keys:
                self._prune(now)
                if len(self._buckets) >= self.max_keys:
                    key = OVERFLOW_KEY
            tokens, updated = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - updated) * self.refill_per_second)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return 0.0
            self._buckets[key] = (tokens, now)
            return (1.0 - tokens) / self.refill_per_second

    def _prune(self, now: float) -> None:
        # A bucket idle long enough to be full again carries no information.
        full_after = self.capacity / self.refill_per_second
        self._pruned_at = now
        self._buckets = {
            k: (tokens, updated)
            for k, (tokens, updated) in self._buckets.items()
            if now - updated < full_after
        }

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)


class AttemptLimiter:
    """At most `max_attempts` attempts per key inside a sliding window (login tries)."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._pruned_at = clock()
        self._lock = threading.Lock()

    def acquire(self, key: str) -> float:
        """Count one attempt before it is checked, so parallel tries cannot outrun the
        limit. Returns 0.0 when the attempt may proceed, else the seconds to wait."""
        with self._lock:
            now = self._clock()
            if now - self._pruned_at >= PRUNE_EVERY_SECONDS:
                self._prune(now)
            if key not in self._attempts and len(self._attempts) >= self.max_keys:
                self._prune(now)
                if len(self._attempts) >= self.max_keys:
                    key = OVERFLOW_KEY
            times = self._attempts.setdefault(key, deque())
            self._expire(times, now)
            if len(times) >= self.max_attempts:
                return max(times[0] + self.window_seconds - now, 0.001)
            times.append(now)
            return 0.0

    def forgive(self, key: str) -> None:
        """Take back the latest attempt (it turned out to be a correct password)."""
        with self._lock:
            times = self._attempts.get(key)
            if times:
                times.pop()
                if not times:
                    del self._attempts[key]

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _expire(self, times: deque[float], now: float) -> None:
        while times and now - times[0] >= self.window_seconds:
            times.popleft()

    def _prune(self, now: float) -> None:
        self._pruned_at = now
        for key in list(self._attempts):
            self._expire(self._attempts[key], now)
            if not self._attempts[key]:
                del self._attempts[key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._attempts)


def retry_after_header(seconds: float) -> str:
    return str(max(1, math.ceil(seconds)))
