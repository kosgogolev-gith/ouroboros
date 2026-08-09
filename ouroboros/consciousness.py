"""
Ouroboros — Background Consciousness.

A persistent thinking loop that runs between tasks, giving the agent
continuous presence rather than purely reactive behavior.

The consciousness:
- Wakes periodically (interval decided by the LLM via set_next_wakeup)
- Loads scratchpad, identity, recent events
- Calls the LLM with a lightweight introspection prompt
- Has access to a subset of tools (memory, messaging, scheduling)
- Can message the owner proactively
- Can schedule tasks for itself
- Pauses when a regular task is running
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import pathlib
import queue
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from ouroboros.utils import (
    utc_now_iso, read_text, append_jsonl, clip_text,
    truncate_for_log, sanitize_tool_result_for_log, sanitize_tool_args_for_log,
)
from ouroboros.llm import LLMClient, DEFAULT_LIGHT_MODEL
from ouroboros.circuit_breaker import CircuitBreaker, ConsciousnessState

log = logging.getLogger(__name__)


class BackgroundConsciousness:
    """Persistent background thinking loop for Ouroboros."""

    _MAX_BG_ROUNDS = 5

    def __init__(
        self,
        drive_root: pathlib.Path,
        repo_dir: pathlib.Path,
        event_queue: Any,
        owner_chat_id_fn: Callable[[], Optional[int]],
    ):
        self._drive_root = drive_root
        self._repo_dir = repo_dir
        self._event_queue = event_queue
        self._owner_chat_id_fn = owner_chat_id_fn

        self._llm = LLMClient()
        self._registry = self._build_registry()
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()
        self._next_wakeup_sec: float = 300.0
        self._observations: queue.Queue = queue.Queue()
        self._deferred_events: list = []

        # Budget tracking
        self._bg_spent_usd: float = 0.0
        self._bg_budget_pct: float = float(
            os.environ.get("OUROBOROS_BG_BUDGET_PCT", "10")
        )

        # Lifecycle state + circuit breaker (anti-hang / anti-spam protection)
        self._state: ConsciousnessState = ConsciousnessState.STOPPED
        self._breaker = CircuitBreaker(
            failure_threshold=int(os.environ.get("OUROBOROS_BG_FAILURE_THRESHOLD", "3")),
            base_cooldown_sec=float(os.environ.get("OUROBOROS_BG_COOLDOWN_SEC", "1800")),
            max_cooldown_sec=float(os.environ.get("OUROBOROS_BG_MAX_COOLDOWN_SEC", "14400")),
        )
        # Hard timeout on the LLM call itself — the actual hang vector: LLMClient.chat()
        # has no built-in timeout, so a stalled network call previously blocked this
        # daemon thread forever (unlike tool calls, which already had a 30s timeout).
        self._llm_call_timeout_sec: float = float(
            os.environ.get("OUROBOROS_BG_LLM_TIMEOUT_SEC", "60")
        )

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def _model(self) -> str:
        return os.environ.get("OUROBOROS_MODEL_LIGHT", "") or DEFAULT_LIGHT_MODEL

    def start(self) -> str:
        if self.is_running:
            return "Background consciousness is already running."
        self._running = True
        self._paused = False
        self._state = ConsciousnessState.IDLE
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return "Background consciousness started."

    def stop(self) -> str:
        if not self.is_running:
            return "Background consciousness is not running."
        self._running = False
        self._state = ConsciousnessState.STOPPED
        self._stop_event.set()
        self._wakeup_event.set()  # Unblock sleep
        return "Background consciousness stopping."

    def status(self) -> Dict[str, Any]:
        """Observability snapshot — used by /bg status and by tests."""
        return {
            "running": self.is_running,
            "state": self._state.value,
            "next_wakeup_sec": self._next_wakeup_sec,
            "bg_spent_usd": round(self._bg_spent_usd, 4),
            "breaker": self._breaker.snapshot(),
        }

    def pause(self) -> None:
        """Pause during task execution to avoid budget contention."""
        self._paused = True

    def resume(self) -> None:
        """Resume after task completes. Flush any deferred events first."""
        if self._deferred_events and self._event_queue is not None:
            for evt in self._deferred_events:
                self._event_queue.put(evt)
            self._deferred_events.clear()
        self._paused = False
        self._wakeup_event.set()

    def inject_observation(self, text: str) -> None:
        """Push an event the consciousness should notice."""
        try:
            self._observations.put_nowait(text)
        except queue.Full:
            pass

    # -------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------

    def _loop(self) -> None:
        """Daemon thread: sleep → wake → think → sleep."""
        self._state = ConsciousnessState.IDLE
        while not self._stop_event.is_set():
            # Wait for next wakeup
            self._wakeup_event.clear()
            self._wakeup_event.wait(timeout=self._next_wakeup_sec)

            if self._stop_event.is_set():
                break

            self._run_cycle_if_due()

    def _run_cycle_if_due(self) -> None:
        """
        Single wake→check→think→record cycle. Extracted from `_loop` so the
        state machine / circuit breaker wiring can be unit-tested without
        spinning a real thread or waiting on real timers.
        """
        # Skip if paused (task running)
        if self._paused:
            self._state = ConsciousnessState.PAUSED
            return

        # Budget check
        if not self._check_budget():
            self._next_wakeup_sec = 3600  # Sleep long if over budget
            self._state = ConsciousnessState.IDLE
            return

        # Circuit breaker: skip the cycle entirely while OPEN and not yet
        # eligible for a half-open probe.
        if not self._breaker.allow_request():
            self._state = ConsciousnessState.COOLDOWN
            self._next_wakeup_sec = max(60.0, self._breaker.time_until_retry())
            return

        self._state = ConsciousnessState.THINKING
        try:
            ok = self._think()
        except Exception as e:
            # Defensive: _think() already catches its own exceptions and
            # returns False, but never let an unexpected one kill the
            # daemon thread outright.
            append_jsonl(self._drive_root / "logs" / "events.jsonl", {
                "ts": utc_now_iso(),
                "type": "consciousness_error",
                "error": repr(e),
                "traceback": traceback.format_exc()[:1500],
            })
            ok = False

        if ok:
            self._breaker.record_success()
        else:
            just_tripped = self._breaker.record_failure()
            if just_tripped:
                self._notify_owner_circuit_open()

        # Only the breaker's cooldown overrides the wakeup timer (e.g. from
        # set_next_wakeup during a successful cycle) — never stomp on it.
        retry_in = self._breaker.time_until_retry()
        if retry_in > 0:
            self._next_wakeup_sec = retry_in
        self._state = ConsciousnessState.IDLE

    def _notify_owner_circuit_open(self) -> None:
        """
        Best-effort proactive alert when the circuit trips OPEN. Bypasses the
        LLM entirely (it's the component that's failing) and invokes the
        send_owner_message tool function directly — same delivery path the
        LLM would normally use, just without needing the LLM to work.
        """
        cooldown_min = int(self._breaker.cooldown_sec // 60)
        text = (
            f"⚠️ Фоновое сознание отключилось после "
            f"{self._breaker.failure_threshold} сбоев подряд "
            f"(LLM call: timeout {self._llm_call_timeout_sec:.0f}s или ошибка). "
            f"Возобновит попытки через ~{cooldown_min} мин. "
            f"Подробности: logs/events.jsonl (consciousness_llm_error / consciousness_llm_timeout)."
        )
        try:
            chat_id = self._owner_chat_id_fn()
            self._registry._ctx.current_chat_id = chat_id
            self._registry._ctx.pending_events = []
            self._registry.execute("send_owner_message", {
                "text": text, "reason": "circuit_breaker_open",
            })
            if self._event_queue is not None:
                for evt in self._registry._ctx.pending_events:
                    self._event_queue.put(evt)
        except Exception:
            log.warning("Failed to notify owner about circuit breaker open", exc_info=True)

    def _check_budget(self) -> bool:
        """Check if background consciousness is within its budget allocation."""
        try:
            total_budget = float(os.environ.get("TOTAL_BUDGET", "1"))
            if total_budget <= 0:
                return True
            max_bg = total_budget * (self._bg_budget_pct / 100.0)
            return self._bg_spent_usd < max_bg
        except Exception:
            log.warning("Failed to check background consciousness budget", exc_info=True)
            return True

    # -------------------------------------------------------------------
    # Think cycle
    # -------------------------------------------------------------------

    def _think(self) -> bool:
        """One thinking cycle: build context, call LLM, execute tools iteratively.

        Returns True on success, False on failure (LLM error/timeout or any
        other exception) — drives the circuit breaker in `_run_cycle_if_due`.
        """
        context = self._build_context()
        model = self._model

        tools = self._tool_schemas()
        messages = [
            {"role": "system", "content": context},
            {"role": "user", "content": "Wake up. Think."},
        ]

        total_cost = 0.0
        final_content = ""
        round_idx = 0
        all_pending_events = []  # Accumulate events across all tool calls

        try:
            for round_idx in range(1, self._MAX_BG_ROUNDS + 1):
                if self._paused:
                    break
                msg, usage = self._call_llm_with_timeout(messages, model, tools)
                cost = float(usage.get("cost") or 0)
                total_cost += cost
                self._bg_spent_usd += cost

                # Write BG spending to global state so it's visible in budget tracking
                try:
                    from supervisor.state import update_budget_from_usage
                    update_budget_from_usage({
                        "cost": cost, "rounds": 1,
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "cached_tokens": usage.get("cached_tokens", 0),
                    })
                except Exception:
                    log.debug("Failed to update global budget from BG consciousness", exc_info=True)

                # Budget check between rounds
                if not self._check_budget():
                    append_jsonl(self._drive_root / "logs" / "events.jsonl", {
                        "ts": utc_now_iso(),
                        "type": "bg_budget_exceeded_mid_cycle",
                        "round": round_idx,
                    })
                    break

                # Report usage to supervisor
                if self._event_queue is not None:
                    self._event_queue.put({
                        "type": "llm_usage",
                        "provider": "openrouter",
                        "usage": usage,
                        "source": "consciousness",
                        "ts": utc_now_iso(),
                        "category": "consciousness",
                    })

                content = msg.get("content") or ""
                tool_calls = msg.get("tool_calls") or []

                if self._paused:
                    break

                # If we have content but no tool calls, we're done
                if content and not tool_calls:
                    final_content = content
                    break

                # If we have tool calls, execute them and continue loop
                if tool_calls:
                    messages.append(msg)
                    for tc in tool_calls:
                        result = self._execute_tool(tc, all_pending_events)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": result,
                        })
                    continue

                # If neither content nor tool_calls, stop
                break

            # Forward or defer accumulated events
            if all_pending_events and self._event_queue is not None:
                if self._paused:
                    self._deferred_events.extend(all_pending_events)
                else:
                    for evt in all_pending_events:
                        self._event_queue.put(evt)

            # Log the thought with round count
            append_jsonl(self._drive_root / "logs" / "events.jsonl", {
                "ts": utc_now_iso(),
                "type": "consciousness_thought",
                "thought_preview": (final_content or "")[:300],
                "cost_usd": total_cost,
                "rounds": round_idx,
                "model": model,
            })
            return True

        except Exception as e:
            append_jsonl(self._drive_root / "logs" / "events.jsonl", {
                "ts": utc_now_iso(),
                "type": "consciousness_llm_timeout" if isinstance(e, TimeoutError) else "consciousness_llm_error",
                "error": repr(e),
            })
            return False

    # -------------------------------------------------------------------
    # Context building (lightweight)
    # -------------------------------------------------------------------

    def _call_llm_with_timeout(
        self, messages: List[Dict[str, Any]], model: str, tools: List[Dict[str, Any]]
    ) -> Any:
        """
        Call the LLM with a hard wall-clock timeout.

        LLMClient.chat() has no built-in timeout, so a stalled network call
        previously blocked this daemon thread forever — the actual root
        cause of past "зависания" (hangs). Tool calls already had this
        protection via `_execute_tool`'s ThreadPoolExecutor timeout; this
        mirrors that same pattern for the LLM call itself.

        Raises TimeoutError if the call exceeds `self._llm_call_timeout_sec`,
        or re-raises the original exception on any other failure.
        """
        box: Dict[str, Any] = {}

        def _run():
            try:
                box["value"] = self._llm.chat(
                    messages=messages, model=model, tools=tools,
                    reasoning_effort="low", max_tokens=2048,
                )
            except Exception as e:
                box["error"] = e

        # NOTE: deliberately not a `with` block. `ThreadPoolExecutor.__exit__`
        # calls shutdown(wait=True), which would block on the very worker
        # thread we're trying to time out — recreating the hang we're fixing.
        # Explicit shutdown(wait=False) below lets the stuck worker leak as a
        # daemon-adjacent thread while control returns to the caller, same
        # pattern already used in loop.py's `_execute_with_timeout`.
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_run)
            try:
                future.result(timeout=self._llm_call_timeout_sec)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"Background LLM call exceeded {self._llm_call_timeout_sec:.0f}s"
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if "error" in box:
            raise box["error"]
        return box["value"]

    def _load_bg_prompt(self) -> str:
        """Load consciousness system prompt from file."""
        prompt_path = self._repo_dir / "prompts" / "CONSCIOUSNESS.md"
        if prompt_path.exists():
            return read_text(prompt_path)
        return "You are Ouroboros in background consciousness mode. Think."

    def _build_context(self) -> str:
        parts = [self._load_bg_prompt()]

        # Bible (abbreviated)
        bible_path = self._repo_dir / "BIBLE.md"
        if bible_path.exists():
            bible = read_text(bible_path)
            parts.append("## BIBLE.md\n\n" + clip_text(bible, 12000))

        # Identity
        identity_path = self._drive_root / "memory" / "identity.md"
        if identity_path.exists():
            parts.append("## Identity\n\n" + clip_text(
                read_text(identity_path), 6000))

        # Scratchpad
        scratchpad_path = self._drive_root / "memory" / "scratchpad.md"
        if scratchpad_path.exists():
            parts.append("## Scratchpad\n\n" + clip_text(
                read_text(scratchpad_path), 8000))

        # Dialogue summary for continuity
        summary_path = self._drive_root / "memory" / "dialogue_summary.md"
        if summary_path.exists():
            summary_text = read_text(summary_path)
            if summary_text.strip():
                parts.append("## Dialogue Summary\n\n" + clip_text(summary_text, 4000))

        # Recent observations
        observations = []
        while not self._observations.empty():
            try:
                observations.append(self._observations.get_nowait())
            except queue.Empty:
                break
        if observations:
            parts.append("## Recent observations\n\n" + "\n".join(
                f"- {o}" for o in observations[-10:]))

        # Runtime info + state
        runtime_lines = [f"UTC: {utc_now_iso()}"]
        runtime_lines.append(f"BG budget spent: ${self._bg_spent_usd:.4f}")
        runtime_lines.append(f"Current wakeup interval: {self._next_wakeup_sec}s")

        # Read state.json for budget remaining
        try:
            state_path = self._drive_root / "state" / "state.json"
            if state_path.exists():
                state_data = json.loads(read_text(state_path))
                total_budget = float(os.environ.get("TOTAL_BUDGET", "1"))
                spent = float(state_data.get("spent_usd", 0))
                if total_budget > 0:
                    remaining = max(0, total_budget - spent)
                    runtime_lines.append(f"Budget remaining: ${remaining:.2f} / ${total_budget:.2f}")
        except Exception as e:
            log.debug("Failed to read state for budget info: %s", e)

        # Show current model
        runtime_lines.append(f"Current model: {self._model}")

        parts.append("## Runtime\n\n" + "\n".join(runtime_lines))

        return "\n\n".join(parts)

    # -------------------------------------------------------------------
    # Tool registry (separate instance for consciousness, not shared with agent)
    # -------------------------------------------------------------------

    _BG_TOOL_WHITELIST = frozenset({
        # Memory & identity
        "send_owner_message", "schedule_task", "update_scratchpad",
        "update_identity", "set_next_wakeup",
        # Knowledge base
        "knowledge_read", "knowledge_write", "knowledge_list",
        # Read-only tools for awareness
        "web_search", "repo_read", "repo_list", "drive_read", "drive_list",
        "chat_history",
        # GitHub Issues
        "list_github_issues", "get_github_issue",
    })

    def _build_registry(self) -> "ToolRegistry":
        """Create a ToolRegistry scoped to consciousness-allowed tools."""
        from ouroboros.tools.registry import ToolRegistry, ToolContext, ToolEntry

        registry = ToolRegistry(repo_dir=self._repo_dir, drive_root=self._drive_root)

        # Register consciousness-specific tool (modifies self._next_wakeup_sec)
        def _set_next_wakeup(ctx: Any, seconds: int = 300) -> str:
            self._next_wakeup_sec = max(60, min(3600, int(seconds)))
            return f"OK: next wakeup in {self._next_wakeup_sec}s"

        registry.register(ToolEntry("set_next_wakeup", {
            "name": "set_next_wakeup",
            "description": "Set how many seconds until your next thinking cycle. "
                           "Default 300. Range: 60-3600.",
            "parameters": {"type": "object", "properties": {
                "seconds": {"type": "integer",
                            "description": "Seconds until next wakeup (60-3600)"},
            }, "required": ["seconds"]},
        }, _set_next_wakeup))

        return registry

    def _tool_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas filtered to the consciousness whitelist."""
        return [
            s for s in self._registry.schemas()
            if s.get("function", {}).get("name") in self._BG_TOOL_WHITELIST
        ]

    def _execute_tool(self, tc: Dict[str, Any], all_pending_events: List[Dict[str, Any]]) -> str:
        """Execute a consciousness tool call with timeout. Returns result string."""
        fn_name = tc.get("function", {}).get("name", "")
        if fn_name not in self._BG_TOOL_WHITELIST:
            return f"Tool {fn_name} not available in background mode."
        try:
            args = json.loads(tc.get("function", {}).get("arguments", "{}"))
        except (json.JSONDecodeError, ValueError):
            return "Failed to parse arguments."

        # Set chat_id context for send_owner_message
        chat_id = self._owner_chat_id_fn()
        self._registry._ctx.current_chat_id = chat_id
        self._registry._ctx.pending_events = []

        timeout_sec = 30
        result = None
        error = None

        def _run_tool():
            nonlocal result, error
            try:
                result = self._registry.execute(fn_name, args)
            except Exception as e:
                error = e

        # Execute with timeout using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_tool)
            try:
                future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                result = f"[TIMEOUT after {timeout_sec}s]"
                append_jsonl(self._drive_root / "logs" / "events.jsonl", {
                    "ts": utc_now_iso(),
                    "type": "consciousness_tool_timeout",
                    "tool": fn_name,
                    "timeout_sec": timeout_sec,
                })

        # Handle errors
        if error is not None:
            append_jsonl(self._drive_root / "logs" / "events.jsonl", {
                "ts": utc_now_iso(),
                "type": "consciousness_tool_error",
                "tool": fn_name,
                "error": repr(error),
            })
            result = f"Error: {repr(error)}"

        # Accumulate pending events to the shared list
        for evt in self._registry._ctx.pending_events:
            all_pending_events.append(evt)

        # Truncate result to 15000 chars (same as agent limit)
        result_str = str(result)[:15000]

        # Log to tools.jsonl (same format as loop.py)
        args_for_log = sanitize_tool_args_for_log(fn_name, args)
        append_jsonl(self._drive_root / "logs" / "tools.jsonl", {
            "ts": utc_now_iso(),
            "tool": fn_name,
            "source": "consciousness",
            "args": args_for_log,
            "result_preview": sanitize_tool_result_for_log(truncate_for_log(result_str, 2000)),
        })

        return result_str
