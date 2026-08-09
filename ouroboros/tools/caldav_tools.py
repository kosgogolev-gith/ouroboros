"""iCloud Calendar tools for Ouroboros via CalDAV."""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

log = logging.getLogger(__name__)

APPLE_ID = os.environ.get("APPLE_ID", "kosgogolev@gmail.com")
CALDAV_URL = "https://caldav.icloud.com"

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _get_caldav_client():
    import caldav
    app_password = os.environ.get("APPLE_APP_PASSWORD", "")
    if not app_password:
        raise RuntimeError("APPLE_APP_PASSWORD not set in environment")
    return caldav.DAVClient(url=CALDAV_URL, username=APPLE_ID, password=app_password)


def _icloud_calendar_list(ctx) -> str:
    """List all iCloud calendars."""
    try:
        client = _get_caldav_client()
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "Нет доступных iCloud календарей."
        lines = ["**iCloud календари:**"]
        for cal in calendars:
            name = cal.get_display_name() or str(cal.url)
            lines.append(f"• {name}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка подключения к iCloud Calendar: {e}"


def _icloud_calendar_today(ctx, calendar_name: str = "") -> str:
    """Get today's events from iCloud Calendar."""
    return _icloud_get_events(ctx, calendar_name=calendar_name, days_ahead=1)


def _icloud_get_events(ctx, calendar_name: str = "", days_ahead: int = 1,
                        max_results: int = 20) -> str:
    """Get upcoming events from iCloud Calendar."""
    try:
        client = _get_caldav_client()
        principal = client.principal()
        calendars = principal.calendars()

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)

        all_events = []
        for cal in calendars:
            name = cal.get_display_name() or ""
            # Filter by calendar name if specified
            if calendar_name and calendar_name.lower() not in name.lower():
                continue
            # Skip reminders
            if "напоминани" in name.lower() or "reminder" in name.lower():
                continue
            try:
                events = cal.date_search(start=now, end=end, expand=True)
                for ev in events:
                    try:
                        comp = ev.icalendar_component
                        summary = str(comp.get("SUMMARY", "(без названия)"))
                        dtstart = comp.get("DTSTART")
                        if dtstart:
                            dt = dtstart.dt
                            if not hasattr(dt, 'hour'):
                                # All-day event
                                start_str = dt.strftime("%d.%m (весь день)")
                            else:
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                start_str = dt.astimezone().strftime("%d.%m %H:%M")
                        else:
                            start_str = "?"
                        location = str(comp.get("LOCATION", ""))
                        loc_str = f" 📍{location}" if location else ""
                        all_events.append((dtstart.dt if dtstart else now, f"• **{start_str}** — {summary}{loc_str} [{name}]"))
                    except Exception:
                        continue
            except Exception:
                continue

        if not all_events:
            period = "сегодня" if days_ahead == 1 else f"ближайшие {days_ahead} дн."
            return f"📅 Нет событий в iCloud Calendar на {period}."

        # Sort by time
        all_events.sort(key=lambda x: x[0] if hasattr(x[0], 'hour') else
                        datetime.combine(x[0], datetime.min.time()).replace(tzinfo=timezone.utc))
        lines = [f"📅 **iCloud события на ближайшие {days_ahead} дн.:**"]
        for _, line in all_events[:max_results]:
            lines.append(line)
        return "\n".join(lines)

    except Exception as e:
        return f"❌ Ошибка получения событий iCloud: {e}"


def _icloud_create_event(ctx, title: str, start_datetime: str, end_datetime: str,
                          description: str = "", location: str = "",
                          calendar_name: str = "Рабочий") -> str:
    """Create event in iCloud Calendar.

    start_datetime / end_datetime format: 'YYYY-MM-DDTHH:MM:SS'
    """
    try:
        from icalendar import Calendar as iCal, Event
        import uuid

        client = _get_caldav_client()
        principal = client.principal()
        calendars = principal.calendars()

        target_cal = None
        for cal in calendars:
            name = cal.get_display_name() or ""
            if calendar_name.lower() in name.lower():
                target_cal = cal
                break

        if not target_cal:
            # Fallback to first non-reminders calendar
            for cal in calendars:
                name = cal.get_display_name() or ""
                if "напоминани" not in name.lower():
                    target_cal = cal
                    break

        if not target_cal:
            return "❌ Не найден подходящий календарь iCloud."

        cal = iCal()
        cal.add("prodid", "-//Ouroboros//iCloud//RU")
        cal.add("version", "2.0")

        event = Event()
        event.add("summary", title)
        event.add("uid", str(uuid.uuid4()))
        event.add("dtstart", datetime.fromisoformat(start_datetime).replace(tzinfo=timezone.utc))
        event.add("dtend", datetime.fromisoformat(end_datetime).replace(tzinfo=timezone.utc))
        if description:
            event.add("description", description)
        if location:
            event.add("location", location)
        event.add("dtstamp", datetime.now(timezone.utc))
        cal.add_component(event)

        target_cal.save_event(cal.to_ical())
        cal_name = target_cal.get_display_name()
        return f"✅ Событие создано в iCloud ({cal_name}): **{title}**"

    except Exception as e:
        return f"❌ Ошибка создания события iCloud: {e}"


def get_tools() -> List:
    if ToolEntry is None:
        return []

    return [
        ToolEntry(
            "icloud_calendar_list",
            {
                "name": "icloud_calendar_list",
                "description": "List all iCloud calendars (Домашний, Рабочий, etc).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            _icloud_calendar_list,
        ),
        ToolEntry(
            "icloud_today",
            {
                "name": "icloud_today",
                "description": "Get today's events from iCloud Calendar. Use for morning briefing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "calendar_name": {"type": "string", "description": "Filter by calendar name (Домашний/Рабочий), empty = all", "default": ""},
                    },
                    "required": [],
                },
            },
            _icloud_calendar_today,
        ),
        ToolEntry(
            "icloud_get_events",
            {
                "name": "icloud_get_events",
                "description": "Get upcoming events from iCloud Calendar for N days ahead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "calendar_name": {"type": "string", "default": ""},
                        "days_ahead": {"type": "integer", "description": "Days to look ahead (1-7)", "default": 1},
                        "max_results": {"type": "integer", "default": 20},
                    },
                    "required": [],
                },
            },
            _icloud_get_events,
        ),
        ToolEntry(
            "icloud_create_event",
            {
                "name": "icloud_create_event",
                "description": "Create a new event in iCloud Calendar (Рабочий or Домашний).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_datetime": {"type": "string", "description": "Format: 2026-08-10T10:00:00"},
                        "end_datetime": {"type": "string", "description": "Format: 2026-08-10T11:00:00"},
                        "description": {"type": "string", "default": ""},
                        "location": {"type": "string", "default": ""},
                        "calendar_name": {"type": "string", "description": "Рабочий or Домашний", "default": "Рабочий"},
                    },
                    "required": ["title", "start_datetime", "end_datetime"],
                },
            },
            _icloud_create_event,
        ),
    ]
