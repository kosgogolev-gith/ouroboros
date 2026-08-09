"""
Tests for background-consciousness resilience: circuit breaker state machine
and the LLM-call timeout that protects against hangs.

Run: python -m pytest tests/test_consciousness_resilience.py -v
"""
import json
import pathlib
import queue
import tempfile
import time

import pytest

from ouroboros.circuit_breaker import BreakerState, CircuitBreaker, ConsciousnessState
from ouroboros.consciousness import BackgroundConsciousness


# ── CircuitBreaker: pure logic, fake clock, no threads ──────────────────

class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make_breaker(**kwargs):
    defaults = dict(failure_threshold=3, base_cooldown_sec=100.0, max_cooldown_sec=400.0)
    defaults.update(kwargs)
    clock = FakeClock()
    return CircuitBreaker(now_fn=clock, **defaults), clock


def test_closed_allows_requests_and_resets_on_success():
    breaker, _ = make_breaker()
    assert breaker.state == BreakerState.CLOSED
    assert breaker.allow_request() is True
    breaker.record_failure()
    breaker.record_success()
    assert breaker.consecutive_failures == 0
    assert breaker.state == BreakerState.CLOSED


def test_opens_after_threshold_consecutive_failures():
    breaker, _ = make_breaker(failure_threshold=3)
    assert breaker.record_failure() is False  # 1
    assert breaker.record_failure() is False  # 2
    tripped = breaker.record_failure()        # 3 -> trips
    assert tripped is True
    assert breaker.state == BreakerState.OPEN
    assert breaker.total_trips == 1


def test_open_blocks_until_cooldown_elapses():
    breaker, clock = make_breaker(failure_threshold=1, base_cooldown_sec=100.0)
    breaker.record_failure()  # trips immediately (threshold=1)
    assert breaker.state == BreakerState.OPEN
    assert breaker.allow_request() is False  # still cooling down

    clock.advance(99.0)
    assert breaker.allow_request() is False  # not yet

    clock.advance(2.0)  # total 101s >= 100s cooldown
    assert breaker.allow_request() is True
    assert breaker.state == BreakerState.HALF_OPEN


def test_half_open_probe_success_closes_circuit():
    breaker, clock = make_breaker(failure_threshold=1, base_cooldown_sec=100.0)
    breaker.record_failure()
    clock.advance(101.0)
    assert breaker.allow_request() is True
    assert breaker.state == BreakerState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == BreakerState.CLOSED
    assert breaker.consecutive_failures == 0
    assert breaker.cooldown_sec == breaker.base_cooldown_sec


def test_half_open_probe_failure_reopens_with_backoff_capped():
    breaker, clock = make_breaker(failure_threshold=1, base_cooldown_sec=100.0, max_cooldown_sec=250.0)
    breaker.record_failure()
    clock.advance(101.0)
    breaker.allow_request()  # -> HALF_OPEN

    just_tripped = breaker.record_failure()  # probe fails
    assert just_tripped is False  # already notified on the original trip
    assert breaker.state == BreakerState.OPEN
    assert breaker.cooldown_sec == 200.0  # doubled

    # Repeat: probe again after new cooldown, fail again -> capped at max
    clock.advance(201.0)
    breaker.allow_request()
    breaker.record_failure()
    assert breaker.cooldown_sec == 250.0  # would be 400 uncapped, capped at max


def test_time_until_retry_reports_zero_when_not_open():
    breaker, _ = make_breaker()
    assert breaker.time_until_retry() == 0.0


def test_snapshot_fields_present():
    breaker, _ = make_breaker(failure_threshold=1)
    breaker.record_failure()
    snap = breaker.snapshot()
    assert snap["state"] == "open"
    assert snap["consecutive_failures"] == 1
    assert snap["total_trips"] == 1
    assert "seconds_until_retry" in snap


# ── BackgroundConsciousness: LLM-call timeout + cycle wiring ────────────

class HangingLLM:
    """Simulates a stalled network call (e.g. dead TCP connection)."""
    def __init__(self, hang_seconds: float):
        self.hang_seconds = hang_seconds
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        time.sleep(self.hang_seconds)
        return {"content": "should never get here", "tool_calls": []}, {"cost": 0}


class FailingLLM:
    """Always raises, simulating a persistent API error."""
    def __init__(self):
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        raise RuntimeError("simulated API failure")


class OkLLM:
    """Returns a clean final response immediately."""
    def chat(self, **kwargs):
        return {"content": "all good", "tool_calls": []}, {"cost": 0.001}


def make_consciousness(tmp_path, llm_timeout_sec=0.2, failure_threshold=2):
    drive_root = tmp_path / "drive"
    repo_dir = tmp_path / "repo"
    (drive_root / "logs").mkdir(parents=True)
    (drive_root / "memory").mkdir(parents=True)
    (drive_root / "state").mkdir(parents=True)
    (repo_dir / "prompts").mkdir(parents=True)

    bc = BackgroundConsciousness(
        drive_root=drive_root,
        repo_dir=repo_dir,
        event_queue=queue.Queue(),
        owner_chat_id_fn=lambda: 12345,
    )
    bc._llm_call_timeout_sec = llm_timeout_sec
    bc._breaker = CircuitBreaker(failure_threshold=failure_threshold, base_cooldown_sec=50.0, max_cooldown_sec=200.0)
    return bc


def test_llm_call_timeout_returns_control_instead_of_hanging(tmp_path):
    """The core anti-hang assertion: a stalled LLM call must not block the
    caller beyond the configured timeout, even though the underlying call
    keeps sleeping for much longer in the background."""
    bc = make_consciousness(tmp_path, llm_timeout_sec=0.2)
    bc._llm = HangingLLM(hang_seconds=5.0)

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        bc._call_llm_with_timeout(messages=[], model="fake/model", tools=[])
    elapsed = time.monotonic() - start

    # Must regain control close to the configured timeout, not the 5s hang.
    assert elapsed < 1.0, f"caller blocked for {elapsed:.2f}s, expected ~0.2s"


def test_think_returns_false_on_timeout_and_logs_event(tmp_path):
    bc = make_consciousness(tmp_path, llm_timeout_sec=0.2)
    bc._llm = HangingLLM(hang_seconds=5.0)

    ok = bc._think()
    assert ok is False

    events_path = bc._drive_root / "logs" / "events.jsonl"
    lines = events_path.read_text().strip().splitlines()
    types = [json.loads(line)["type"] for line in lines]
    assert "consciousness_llm_timeout" in types


def test_think_returns_true_on_success(tmp_path):
    bc = make_consciousness(tmp_path)
    bc._llm = OkLLM()
    assert bc._think() is True


def test_run_cycle_if_due_skips_when_paused(tmp_path):
    bc = make_consciousness(tmp_path)
    bc._llm = OkLLM()
    bc.pause()
    bc._run_cycle_if_due()
    assert bc._state == ConsciousnessState.PAUSED


def test_run_cycle_if_due_trips_breaker_after_repeated_failures_and_notifies_once(tmp_path):
    """Integration of the state machine + circuit breaker without any real
    thread/timer: repeated failing cycles must trip OPEN exactly once and
    queue exactly one owner notification, not one per failure."""
    bc = make_consciousness(tmp_path, llm_timeout_sec=0.1, failure_threshold=2)
    bc._llm = FailingLLM()

    bc._run_cycle_if_due()  # failure 1 — breaker still closed
    assert bc._breaker.state == BreakerState.CLOSED

    bc._run_cycle_if_due()  # failure 2 — trips OPEN, should notify once
    assert bc._breaker.state == BreakerState.OPEN

    bc._run_cycle_if_due()  # breaker OPEN and cooldown not elapsed -> cycle skipped entirely
    assert bc._llm.calls == 2, "no additional LLM call should happen while circuit is OPEN"
    assert bc._state == ConsciousnessState.COOLDOWN

    # Exactly one proactive owner message should have been queued (dedup).
    notifications = []
    while not bc._event_queue.empty():
        evt = bc._event_queue.get_nowait()
        if evt.get("type") == "send_message":
            notifications.append(evt)
    assert len(notifications) == 1
    assert "сбоев подряд" in notifications[0]["text"]


def test_run_cycle_if_due_recovers_after_cooldown_via_half_open_probe(tmp_path):
    bc = make_consciousness(tmp_path, llm_timeout_sec=0.1, failure_threshold=1)
    bc._llm = FailingLLM()

    bc._run_cycle_if_due()  # trips OPEN immediately (threshold=1)
    assert bc._breaker.state == BreakerState.OPEN

    # Simulate cooldown elapsing by rewinding the breaker's clock reference.
    bc._breaker._opened_at -= (bc._breaker.cooldown_sec + 1)

    bc._llm = OkLLM()  # the underlying issue is "fixed"
    bc._run_cycle_if_due()  # should allow a half-open probe and succeed
    assert bc._breaker.state == BreakerState.CLOSED
    assert bc._state == ConsciousnessState.IDLE


def test_successful_cycle_does_not_override_llm_chosen_wakeup_interval(tmp_path):
    """A successful cycle must not stomp on set_next_wakeup's value."""
    bc = make_consciousness(tmp_path)
    bc._llm = OkLLM()
    bc._next_wakeup_sec = 777.0  # simulate LLM having called set_next_wakeup
    bc._run_cycle_if_due()
    assert bc._next_wakeup_sec == 777.0
