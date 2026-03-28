"""
Supervisor — State management.

Persistent state on Google Drive: load, save, atomic writes, file locks.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import pathlib
import time
import uuid
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level config (set via init())
# ---------------------------------------------------------------------------
DRIVE_ROOT: pathlib.Path = pathlib.Path("/content/drive/MyDrive/Ouroboros")
STATE_PATH: pathlib.Path = DRIVE_ROOT / "state" / "state.json"
STATE_LAST_GOOD_PATH: pathlib.Path = DRIVE_ROOT / "state" / "state.last_good.json"
STATE_LOCK_PATH: pathlib.Path = DRIVE_ROOT / "locks" / "state.lock"
QUEUE_SNAPSHOT_PATH: pathlib.Path = DRIVE_ROOT / "state" / "queue_snapshot.json"


def init(drive_root: pathlib.Path, total_budget_limit: float = 0.0) -> None:
    global DRIVE_ROOT, STATE_PATH, STATE_LAST_GOOD_PATH, STATE_LOCK_PATH, QUEUE_SNAPSHOT_PATH
    DRIVE_ROOT = drive_root
    STATE_PATH = drive_root / "state" / "state.json"
    STATE_LAST_GOOD_PATH = drive_root / "state" / "state.last_good.json"
    STATE_LOCK_PATH = drive_root / "locks" / "state.lock"
    QUEUE_SNAPSHOT_PATH = drive_root / "state" / "queue_snapshot.json"
    set_budget_limit(total_budget_limit)


# ---------------------------------------------------------------------------
# Atomic file operations
# ---------------------------------------------------------------------------

def atomic_write_text(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{uuid.uuid4().hex}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        data = content.encode("utf-8")
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))


def json_load_file(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        log.debug(f"Failed to load JSON from {path}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# File locks
# ---------------------------------------------------------------------------

def acquire_file_lock(lock_path: pathlib.Path, timeout_sec: float = 4.0,
                      stale_sec: float = 90.0) -> Optional[int]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    while (time.time() - started) < timeout_sec:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, f"pid={os.getpid()} ts={datetime.datetime.now(datetime.timezone.utc).isoformat()}\n".encode("utf-8"))
            except Exception:
                log.debug(f"Failed to write lock metadata to {lock_path}", exc_info=True)
                pass
            return fd
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > stale_sec:
                    lock_path.unlink()
                    continue
            except Exception:
                log.debug(f"Failed to check/remove stale lock at {lock_path}", exc_info=True)
                pass
            time.sleep(0.05)
        except Exception:
            log.warning(f"Failed to acquire lock at {lock_path}", exc_info=True)
            break
    return None


def release_file_lock(lock_path: pathlib.Path, lock_fd: Optional[int]) -> None:
    if lock_fd is None:
        return
    try:
        os.close(lock_fd)
    except Exception:
        log.debug(f"Failed to close lock fd {lock_fd} for {lock_path}", exc_info=True)
        pass
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        log.debug(f"Failed to unlink lock file {lock_path}", exc_info=True)
        pass


# Re-export append_jsonl from ouroboros.utils (single source of truth)
from ouroboros.utils import append_jsonl  # noqa: F401


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

def ensure_state_defaults(st: Dict[str, Any]) -> Dict[str, Any]:
    st.setdefault("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    st.setdefault("owner_id", None)
    st.setdefault("owner_chat_id", None)
    st.setdefault("tg_offset", 0)
    st.setdefault("spent_usd", 0.0)
    st.setdefault("spent_calls", 0)
    st.setdefault("spent_tokens_prompt", 0)
    st.setdefault("spent_tokens_completion", 0)
    st.setdefault("spent_tokens_cached", 0)
    st.setdefault("session_id", uuid.uuid4().hex)
    st.setdefault("current_branch", None)
    st.setdefault("current_sha", None)
    st.setdefault("last_owner_message_at", "")
    st.setdefault("last_evolution_task_at", "")
    st.setdefault("budget_messages_since_report", 0)
    st.setdefault("evolution_mode_enabled", False)
    st.setdefault("evolution_cycle", 0)
    st.setdefault("session_total_snapshot", None)
    st.setdefault("session_spent_snapshot", None)
    st.setdefault("budget_drift_pct", None)
    st.setdefault("budget_drift_alert", False)
    st.setdefault("evolution_consecutive_failures", 0)
    for legacy_key in ("approvals", "idle_cursor", "idle_stats", "last_idle_task_at",
                        "last_auto_review_at", "last_review_task_id", "session_daily_snapshot"):
        st.pop(legacy_key, None)
    return st


def default_state_dict() -> Dict[str, Any]:
    """Create a fresh state dict. Single source of truth: ensure_state_defaults."""
    return ensure_state_defaults({})


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def _load_state_unlocked() -> Dict[str, Any]:
    """Load state without acquiring lock. Caller must hold STATE_LOCK."""
    recovered = False
    st_obj = json_load_file(STATE_PATH)
    if st_obj is None:
        st_obj = json_load_file(STATE_LAST_GOOD_PATH)
        recovered = st_obj is not None

    if st_obj is None:
        st = ensure_state_defaults(default_state_dict())
        _save_state_unlocked(st)
        return st

    st = ensure_state_defaults(st_obj)
    if recovered:
        _save_state_unlocked(st)
    return st


def _save_state_unlocked(st: Dict[str, Any]) -> None:
    """Save state without acquiring lock. Caller must hold STATE_LOCK."""
    st = ensure_state_defaults(st)
    payload = json.dumps(st, ensure_ascii=False, indent=2)
    atomic_write_text(STATE_PATH, payload)
    atomic_write_text(STATE_LAST_GOOD_PATH, payload)


def load_state() -> Dict[str, Any]:
    lock_fd = acquire_file_lock(STATE_LOCK_PATH)
    try:
        return _load_state_unlocked()
    finally:
        release_file_lock(STATE_LOCK_PATH, lock_fd)


def save_state(st: Dict[str, Any]) -> None:
    lock_fd = acquire_file_lock(STATE_LOCK_PATH)
    try:
        _save_state_unlocked(st)
    finally:
        release_file_lock(STATE_LOCK_PATH, lock_fd)


def init_state() -> Dict[str, Any]:
    """
    Initialize state at session start, capturing snapshots for budget drift detection.

    Fetches OpenRouter ground truth and stores session_daily_snapshot and
    session_spent_snapshot for drift calculation.
    """
    lock_fd = acquire_file_lock(STATE_LOCK_PATH)
    try:
        st = _load_state_unlocked()

        # Capture session snapshots for drift detection
        st["session_spent_snapshot"] = float(st.get("spent_usd") or 0.0)

        # Fetch OpenRouter ground truth to capture total_usd baseline
        ground_truth = check_openrouter_ground_truth()
        if ground_truth is not None:
            st["session_total_snapshot"] = ground_truth["total_usd"]
            st["openrouter_total_usd"] = ground_truth["total_usd"]
            st["openrouter_daily_usd"] = ground_truth["daily_usd"]
            st["openrouter_last_check_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        else:
            # If we can't fetch ground truth, use 0 as baseline
            st["session_total_snapshot"] = 0.0

        # Reset drift tracking
        st["budget_drift_pct"] = None
        st["budget_drift_alert"] = False

        _save_state_unlocked(st)
        return st
    finally:
        release_file_lock(STATE_LOCK_PATH, lock_fd)


# ---------------------------------------------------------------------------
# Budget tracking (moved from workers.py)
# ---------------------------------------------------------------------------
TOTAL_BUDGET_LIMIT: float = 0.0
EVOLUTION_BUDGET_RESERVE: float = 50.0  # Stop evolution when remaining < this


def set_budget_limit(limit: float) -> None:
    """Set total budget limit for budget_pct calculation."""
    global TOTAL_BUDGET_LIMIT
    TOTAL_BUDGET_LIMIT = limit


def budget_remaining(st: Dict[str, Any]) -> float:
    """Calculate remaining budget in USD."""
    spent = float(st.get("spent_usd") or 0.0)
    total = float(TOTAL_BUDGET_LIMIT or 0.0)
    if total <= 0:
        return float('inf')  # No limit set
    return max(0.0, total - spent)


def check_openrouter_ground_truth() -> Optional[Dict[str, float]]:
    """
    Call OpenRouter API to get ground truth usage.

    Returns dict with total_usd and daily_usd spent according to OpenRouter, or None on error.
    """
    try:
        import urllib.request
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # OpenRouter API returns usage already in dollars (not cents)
        usage_total = data.get("data", {}).get("usage", 0)
        usage_daily = data.get("data", {}).get("usage_daily", 0)
        return {
            "total_usd": float(usage_total),
            "daily_usd": float(usage_daily),
        }
    except Exception:
        log.warning("Failed to fetch OpenRouter ground truth", exc_info=True)
        return None


def budget_pct(st: Dict[str, Any]) -> float:
    """Calculate budget percentage used."""
    spent = float(st.get("spent_usd") or 0.0)
    total = float(TOTAL_BUDGET_LIMIT or 0.0)
    if total <= 0:
        return 0.0
    return (spent / total) * 100.0


def update_budget_from_usage(usage: Dict[str, Any]) -> None:
    """Update state with LLM usage costs and tokens.

    Uses a single lock scope for the read-modify-write cycle to prevent
    concurrent writes from losing budget updates.

    Every 50 calls, fetches OpenRouter ground truth for comparison.
    """
    def _to_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            log.debug(f"Failed to convert value to float: {v!r}", exc_info=True)
            return default

    def _to_int(v: Any, default: int = 0) -> int:
        try:
            return int(v)
        except Exception:
            log.debug(f"Failed to convert value to int: {v!r}", exc_info=True)
            return default

    # Step 1: Update budget counters under lock (fast, no I/O beyond Drive)
    lock_fd = acquire_file_lock(STATE_LOCK_PATH)
    try:
        st = _load_state_unlocked()
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if cost is None:
            cost = 0.0
        st["spent_usd"] = _to_float(st.get("spent_usd") or 0.0) + _to_float(cost)
        rounds = _to_int(usage.get("rounds") if isinstance(usage, dict) else 0, default=1)
        st["spent_calls"] = int(st.get("spent_calls") or 0) + rounds
        st["spent_tokens_prompt"] = _to_int(st.get("spent_tokens_prompt") or 0) + _to_int(
            usage.get("prompt_tokens") if isinstance(usage, dict) else 0)
        st["spent_tokens_completion"] = _to_int(st.get("spent_tokens_completion") or 0) + _to_int(
            usage.get("completion_tokens") if isinstance(usage, dict) else 0)
        st["spent_tokens_cached"] = _to_int(st.get("spent_tokens_cached") or 0) + _to_int(
            usage.get("cached_tokens") if isinstance(usage, dict) else 0)
        should_check_ground_truth = (st["spent_calls"] % 50 == 0)
        _save_state_unlocked(st)
    finally:
        release_file_lock(STATE_LOCK_PATH, lock_fd)

    # Step 2: HTTP to OpenRouter OUTSIDE the lock (can take up to 10s)
    if should_check_ground_truth:
        ground_truth = check_openrouter_ground_truth()
        if ground_truth is not None:
            lock_fd = acquire_file_lock(STATE_LOCK_PATH)
            try:
                st = _load_state_unlocked()
                st["openrouter_total_usd"] = ground_truth["total_usd"]
                st["openrouter_daily_usd"] = ground_truth["daily_usd"]
                st["openrouter_last_check_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

                session_total_snap = st.get("session_total_snapshot")
                session_spent_snap = st.get("session_spent_snapshot")

                if session_total_snap is not None and session_spent_snap is not None:
                    current_total_usd = ground_truth["total_usd"]
                    current_spent_usd = _to_float(st.get("spent_usd") or 0.0)
                    or_delta = current_total_usd - _to_float(session_total_snap)
                    our_delta = current_spent_usd - _to_float(session_spent_snap)

                    if or_delta > 0.001:
                        drift_pct = abs(or_delta - our_delta) / max(abs(or_delta), 0.01) * 100.0
                        st["budget_drift_pct"] = drift_pct
                        abs_diff = abs(or_delta - our_delta)
                        if drift_pct > 50.0 and abs_diff > 5.0:
                            st["budget_drift_alert"] = True
                            append_jsonl(
                                DRIVE_ROOT / "logs" / "events.jsonl",
                                {
                                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    "event": "budget_drift_warning",
                                    "drift_pct": round(drift_pct, 2),
                                    "our_delta": round(our_delta, 4),
                                    "or_delta": round(or_delta, 4),
                                    "abs_diff": round(abs_diff, 4),
                                    "spent_calls": st["spent_calls"],
                                    "note": "High drift detected",
                                },
                            )
                _save_state_unlocked(st)
            finally:
                release_file_lock(STATE_LOCK_PATH, lock_fd)


def rotate_chat_log_if_needed(max_mb: float = 10.0, keep_files: int = 5) -> None:
    """Rotate chat.jsonl if it exceeds max_mb (megabytes). Keep most recent keep_files."""
    log_path = DRIVE_ROOT / "logs" / "chat.jsonl"
    if not log_path.exists():
        return
    try:
        size_mb = log_path.stat().st_size / (1024 * 1024)
        if size_mb < max_mb:
            return
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = DRIVE_ROOT / "logs" / f"chat.{ts}.jsonl"
        log_path.rename(archive_path)
        log_path.write_text("", encoding="utf-8")
        # prune old archives
        archives = sorted((DRIVE_ROOT / "logs").glob("chat.*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[keep_files:]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        log.warning("Failed to rotate chat log", exc_info=True)


def status_text() -> str:
    st = load_state()
    spent = float(st.get("spent_usd") or 0.0)
    total = float(os.environ.get("TOTAL_BUDGET", "0") or 0.0)
    if total <= 0:
        total = float(st.get("total_budget_limit", 0))
    if total <= 0:
        total = 30.0  # default display

    pct = (spent / total) * 100 if total > 0 else 0.0
    remaining = max(0.0, total - spent)
    return f"💰 ${spent:.2f} / ${total:.2f} ({pct:.1f}%), rem ${remaining:.2f}"