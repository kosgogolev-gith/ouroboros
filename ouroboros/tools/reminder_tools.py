"""Reminder tools — set time-based reminders, checked on each Ouroboros wakeup."""
import json
import logging
import os
import pathlib
from datetime import datetime, timedelta
from typing import List

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None

REMINDERS_FILE = pathlib.Path.home() / "ouroboros_data" / "reminders.json"


def _load_reminders() -> list:
    try:
        if REMINDERS_FILE.exists():
            return json.loads(REMINDERS_FILE.read_text())
    except Exception:
        pass
    return []


def _save_reminders(reminders: list) -> None:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(json.dumps(reminders, ensure_ascii=False, indent=2))


def _reminder_set(ctx, text: str, delay_minutes: int = 0, at: str = "") -> str:
    """Set a reminder. Provide either delay_minutes or at (HH:MM or YYYY-MM-DDTHH:MM)."""
    now = datetime.now()

    if delay_minutes > 0:
        fire_at = now + timedelta(minutes=delay_minutes)
        display = f"через {delay_minutes} мин. ({fire_at.strftime('%H:%M')})"
    elif at:
        try:
            if "T" in at or "-" in at[:4]:
                fire_at = datetime.fromisoformat(at)
            else:
                t = datetime.strptime(at, "%H:%M")
                fire_at = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                if fire_at <= now:
                    fire_at += timedelta(days=1)
            display = f"в {fire_at.strftime('%d.%m %H:%M')}"
        except Exception as e:
            return f"❌ Неверный формат времени: {e}. Используй HH:MM или YYYY-MM-DDTHH:MM"
    else:
        return "❌ Укажи delay_minutes или at"

    reminders = _load_reminders()
    reminders.append({
        "text": text,
        "fire_at": fire_at.isoformat(),
        "created_at": now.isoformat(),
    })
    _save_reminders(reminders)
    return f"⏰ Напоминание установлено: **{text}** — {display}"


def _reminder_list(ctx) -> str:
    """List all pending reminders."""
    reminders = _load_reminders()
    now = datetime.now()
    pending = [r for r in reminders if datetime.fromisoformat(r["fire_at"]) > now]
    if not pending:
        return "📭 Нет активных напоминаний."
    lines = [f"**Напоминания ({len(pending)}):**"]
    for r in sorted(pending, key=lambda x: x["fire_at"]):
        fire = datetime.fromisoformat(r["fire_at"]).strftime("%d.%m %H:%M")
        lines.append(f"• {fire} — {r['text']}")
    return "\n".join(lines)


def _reminder_check(ctx) -> str:
    """Check and fire due reminders. Call this on each wakeup."""
    reminders = _load_reminders()
    now = datetime.now()
    fired = []
    remaining = []

    for r in reminders:
        if datetime.fromisoformat(r["fire_at"]) <= now:
            fired.append(r)
        else:
            remaining.append(r)

    if not fired:
        return ""

    _save_reminders(remaining)

    # Send notifications
    messages = []
    for r in fired:
        messages.append(f"⏰ **Напоминание:** {r['text']}")

    result = "\n".join(messages)

    # Try to send via Telegram
    try:
        import sys
        tg_mod = sys.modules.get("supervisor.telegram") or sys.modules.get("__main__")
        if tg_mod and hasattr(tg_mod, "TG") and tg_mod.TG:
            import json as _json, pathlib as _pl
            state = _json.loads((_pl.Path.home() / "ouroboros_data" / "state" / "state.json").read_text())
            chat_id = state.get("owner_chat_id")
            if chat_id:
                for r in fired:
                    tg_mod.TG.send_message(chat_id, f"⏰ Напоминание: {r['text']}")
    except Exception as e:
        log.debug("Could not send reminder via TG: %s", e)

    return result


def _reminder_delete(ctx, text: str) -> str:
    """Delete a reminder by text (partial match)."""
    reminders = _load_reminders()
    before = len(reminders)
    reminders = [r for r in reminders if text.lower() not in r["text"].lower()]
    _save_reminders(reminders)
    deleted = before - len(reminders)
    return f"✅ Удалено {deleted} напоминаний." if deleted else f"❌ Напоминания с текстом '{text}' не найдены."


def get_tools() -> List:
    if ToolEntry is None:
        return []
    return [
        ToolEntry(
            "reminder_set",
            {
                "name": "reminder_set",
                "description": (
                    "Set a reminder that fires at a specific time or after a delay. "
                    "Reminders are checked on each Ouroboros wakeup and sent via Telegram. "
                    "Use delay_minutes for relative time, or at for absolute (HH:MM or YYYY-MM-DDTHH:MM)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Reminder text"},
                        "delay_minutes": {"type": "integer", "description": "Fire after N minutes", "default": 0},
                        "at": {"type": "string", "description": "Fire at time: HH:MM or YYYY-MM-DDTHH:MM", "default": ""},
                    },
                    "required": ["text"],
                },
            },
            _reminder_set,
        ),
        ToolEntry(
            "reminder_list",
            {
                "name": "reminder_list",
                "description": "List all pending reminders.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _reminder_list,
        ),
        ToolEntry(
            "reminder_check",
            {
                "name": "reminder_check",
                "description": "Check and fire due reminders. Called automatically on wakeup.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _reminder_check,
        ),
        ToolEntry(
            "reminder_delete",
            {
                "name": "reminder_delete",
                "description": "Delete a reminder by partial text match.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to match"},
                    },
                    "required": ["text"],
                },
            },
            _reminder_delete,
        ),
    ]
