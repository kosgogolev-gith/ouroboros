"""Google Calendar tools for Ouroboros — uses existing OAuth token."""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _get_calendar_service():
    """Build Google Calendar API service using existing OAuth token."""
    import sys
    import types
    import pathlib
    # Ensure google.colab stub exists
    if "google.colab" not in sys.modules:
        sys.modules["google.colab"] = types.ModuleType("google.colab")

    # Use VPS token directly, bypassing Colab auth
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = pathlib.Path.home() / "ouroboros_data" / "tokens" / "google_token.json"
    SCOPES = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ]
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            pass
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _calendar_list(ctx) -> str:
    """List available calendars."""
    try:
        svc = _get_calendar_service()
        result = svc.calendarList().list().execute()
        items = result.get("items", [])
        if not items:
            return "Нет доступных календарей."
        lines = ["**Доступные календари:**"]
        for c in items:
            primary = " (основной)" if c.get("primary") else ""
            lines.append(f"• `{c['id']}` — {c['summary']}{primary}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка получения календарей: {e}"


def _calendar_get_events(ctx, calendar_id: str = "primary",
                          days_ahead: int = 1, max_results: int = 10) -> str:
    """Get upcoming events from Google Calendar."""
    try:
        svc = _get_calendar_service()
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        result = svc.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        if not events:
            period = "сегодня" if days_ahead == 1 else f"ближайшие {days_ahead} дн."
            return f"📅 Нет событий на {period}."

        lines = [f"📅 **События на ближайшие {days_ahead} дн.:**"]
        for ev in events:
            start = ev["start"].get("dateTime", ev["start"].get("date", ""))
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                start_str = dt.astimezone().strftime("%d.%m %H:%M")
            except Exception:
                start_str = start
            title = ev.get("summary", "(без названия)")
            location = f" 📍{ev['location']}" if ev.get("location") else ""
            lines.append(f"• **{start_str}** — {title}{location}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка получения событий: {e}"


def _calendar_create(ctx, title: str, start_datetime: str, end_datetime: str,
                     description: str = "", location: str = "",
                     calendar_id: str = "primary") -> str:
    """Create a new event in Google Calendar.

    start_datetime / end_datetime format: 'YYYY-MM-DDTHH:MM:SS' (local Moscow time)
    """
    try:
        svc = _get_calendar_service()
        event = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_datetime, "timeZone": "Europe/Moscow"},
            "end": {"dateTime": end_datetime, "timeZone": "Europe/Moscow"},
        }
        created = svc.events().insert(calendarId=calendar_id, body=event).execute()
        link = created.get("htmlLink", "")
        return f"✅ Событие создано: **{title}**\n🔗 {link}"
    except Exception as e:
        return f"❌ Ошибка создания события: {e}"


def _calendar_delete(ctx, event_id: str, calendar_id: str = "primary") -> str:
    """Delete an event by ID."""
    try:
        svc = _get_calendar_service()
        svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return f"✅ Событие {event_id} удалено."
    except Exception as e:
        return f"❌ Ошибка удаления: {e}"


def _calendar_today(ctx, calendar_id: str = "primary") -> str:
    """Get today's events — shortcut for morning briefing."""
    return _calendar_get_events(ctx, calendar_id=calendar_id, days_ahead=1, max_results=15)


def get_tools() -> List:
    if ToolEntry is None:
        return []

    return [
        ToolEntry(
            "calendar_list",
            {
                "name": "calendar_list",
                "description": "List all available Google Calendars.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _calendar_list,
        ),
        ToolEntry(
            "calendar_today",
            {
                "name": "calendar_today",
                "description": "Get today's events from Google Calendar. Use for morning briefing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                    "required": [],
                },
            },
            _calendar_today,
        ),
        ToolEntry(
            "calendar_get_events",
            {
                "name": "calendar_get_events",
                "description": "Get upcoming events from Google Calendar for N days ahead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "days_ahead": {"type": "integer", "description": "Days to look ahead (1-7)", "default": 1},
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
            },
            _calendar_get_events,
        ),
        ToolEntry(
            "calendar_create",
            {
                "name": "calendar_create",
                "description": "Create a new event in Google Calendar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_datetime": {"type": "string", "description": "Format: 2026-08-09T10:00:00"},
                        "end_datetime": {"type": "string", "description": "Format: 2026-08-09T11:00:00"},
                        "description": {"type": "string", "default": ""},
                        "location": {"type": "string", "default": ""},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                    "required": ["title", "start_datetime", "end_datetime"],
                },
            },
            _calendar_create,
        ),
        ToolEntry(
            "calendar_delete",
            {
                "name": "calendar_delete",
                "description": "Delete a Google Calendar event by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                    "required": ["event_id"],
                },
            },
            _calendar_delete,
        ),
    ]
