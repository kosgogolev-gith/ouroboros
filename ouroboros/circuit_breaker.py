"""
Ouroboros — Circuit breaker + lifecycle state machine for background consciousness.

Kept in its own module (no threads, no LLM client, no Drive paths) so the
failure/backoff logic can be unit-tested in isolation from the daemon thread
in consciousness.py.
"""

from __future__ import annotations

import enum
import time
from typing import Callable, Optional


class ConsciousnessState(str, enum.Enum):
    """Lifecycle state of the background consciousness thread."""
    STOPPED = "stopped"
    IDLE = "idle"          # sleeping, waiting for next wakeup
    THINKING = "thinking"  # actively running a think cycle
    PAUSED = "paused"      # a foreground task is running, cycle skipped
    COOLDOWN = "cooldown"  # circuit open, backing off before retry


class BreakerState(str, enum.Enum):
    CLOSED = "closed"        # normal operation, every cycle allowed
    OPEN = "open"             # tripped, rejecting cycles until cooldown elapses
    HALF_OPEN = "half_open"   # cooldown elapsed, single probe cycle allowed


class CircuitBreaker:
    """
    Closed/open/half-open circuit breaker adapted for a periodic background
    loop (one "request" per wakeup cycle) instead of per-call RPC.

    - CLOSED: every cycle allowed. `failure_threshold` consecutive failures
      trips to OPEN.
    - OPEN: no cycles allowed until `cooldown_sec` has elapsed since the
      trip. Cooldown grows exponentially on repeated trips (capped at
      `max_cooldown_sec`) so a persistent outage doesn't burn budget or spam
      logs/owner.
    - HALF_OPEN: exactly one probe cycle is allowed once the cooldown has
      elapsed. Success -> CLOSED (counters and cooldown reset to base).
      Failure -> OPEN again with cooldown doubled.

    Not thread-safe for concurrent callers — intended to be driven from a
    single background thread (the consciousness loop).
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        base_cooldown_sec: float = 1800.0,
        max_cooldown_sec: float = 14400.0,
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.base_cooldown_sec = base_cooldown_sec
        self.max_cooldown_sec = max_cooldown_sec
        self._now = now_fn

        self.state = BreakerState.CLOSED
        self.consecutive_failures = 0
        self.cooldown_sec = base_cooldown_sec
        self.total_trips = 0
        self._opened_at: Optional[float] = None

    def allow_request(self) -> bool:
        """Whether a think-cycle may run right now."""
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            if self._opened_at is not None and (self._now() - self._opened_at) >= self.cooldown_sec:
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: a probe was already granted; block further concurrent probes.
        return False

    def record_success(self) -> None:
        """Cycle succeeded — reset everything back to a healthy CLOSED state."""
        self.consecutive_failures = 0
        self.cooldown_sec = self.base_cooldown_sec
        self.state = BreakerState.CLOSED
        self._opened_at = None

    def record_failure(self) -> bool:
        """
        Record a failed cycle.

        Returns True exactly on the call that trips the breaker OPEN for
        the first time (from CLOSED) — the caller should notify the owner
        once on that transition, not on every subsequent failure.
        """
        if self.state == BreakerState.HALF_OPEN:
            # Probe failed: reopen with backed-off cooldown. Already notified
            # the owner on the original trip — don't spam on every reopen.
            self.cooldown_sec = min(self.cooldown_sec * 2, self.max_cooldown_sec)
            self.state = BreakerState.OPEN
            self._opened_at = self._now()
            self.total_trips += 1
            return False

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.state = BreakerState.OPEN
            self._opened_at = self._now()
            self.total_trips += 1
            return True
        return False

    def time_until_retry(self) -> float:
        """Seconds until the next cycle may run. 0 if allowed right now."""
        if self.state != BreakerState.OPEN or self._opened_at is None:
            return 0.0
        remaining = self.cooldown_sec - (self._now() - self._opened_at)
        return max(0.0, remaining)

    def snapshot(self) -> dict:
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "cooldown_sec": self.cooldown_sec,
            "total_trips": self.total_trips,
            "seconds_until_retry": round(self.time_until_retry(), 1),
        }
