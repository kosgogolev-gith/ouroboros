"""Google Calendar API integration.

Provides functions to list, get, create, update, and delete calendar events.
Built on top of the google-api-python-client with proper authentication.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .auth import authenticate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# Scopes for Calendar API - need read/write for full functionality
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Cache the service client
_calendar_service: Optional[Any] = None


def get_calendar_service() -> Optional[Any]:
    """
    Return an authenticated Calendar API service client, or None if auth fails.

    The service is cached after first successful creation.

    Returns:
        Google Calendar service client or None if unavailable.
    """
    global _calendar_service
    if _calendar_service is not None:
        return _calendar_service

    try:
        creds = authenticate()
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        _calendar_service = service
        log.info("Calendar service initialized")
        return service
    except Exception as e:
        log.error(f"Failed to initialize Calendar service: {e}")
        return None


def _parse_datetime(dt_str: Union[str, datetime]) -> str:
    """
    Convert datetime input to RFC3339 ISO string for Calendar API.

    Args:
        dt_str: ISO string or datetime object

    Returns:
        RFC3339 formatted string with 'Z' suffix for UTC if no timezone
    """
    if isinstance(dt_str, datetime):
        # If naive datetime, assume UTC
        if dt_str.tzinfo is None:
            dt_str = dt_str.replace(tzinfo=timezone.utc)
        return dt_str.isoformat()
    # String input - ensure it's RFC3339 compliant
    # Calendar API expects RFC3339, e.g., "2024-03-20T10:00:00Z" or with timezone offset
    if dt_str.endswith("Z") or "+" in dt_str or dt_str.count("-") > 2:
        return dt_str
    # If just date/time without timezone, append Z to treat as UTC
    return dt_str + "Z"


def list_events(
    time_min: Optional[Union[str, datetime]] = None,
    time_max: Optional[Union[str, datetime]] = None,
    max_results: int = 100,
    calendar_id: str = "primary",
) -> List[Dict[str, Any]]:
    """
    List events from a calendar within a time range.

    Args:
        time_min: Start time (inclusive). ISO string or datetime. Default: now.
        time_max: End time (exclusive). ISO string or datetime.
        max_results: Maximum number of events to return (max 2500 per API).
        calendar_id: Calendar ID (default: "primary").

    Returns:
        List of event resources (dictionaries).

    Raises:
        RuntimeError: If Calendar API is unavailable.
        HttpError: On API failures.
    """
    service = get_calendar_service()
    if not service:
        raise RuntimeError("Google Calendar API not available — authentication failed")

    # Set defaults
    if time_min is None:
        time_min = datetime.utcnow()
    time_min_iso = _parse_datetime(time_min)
    time_max_iso = _parse_datetime(time_max) if time_max else None

    params = {
        "calendarId": calendar_id,
        "timeMin": time_min_iso,
        "maxResults": min(max_results, 2500),
        "singleEvents": True,  # Expand recurring events into instances
        "orderBy": "startTime",
    }
    if time_max_iso:
        params["timeMax"] = time_max_iso

    try:
        events_result = service.events().list(**params).execute()
        events = events_result.get("items", [])
        log.info(f"Retrieved {len(events)} events from calendar {calendar_id}")
        return events
    except HttpError as e:
        log.error(f"API error listing events: {e}")
        raise


def get_event(event_id: str, calendar_id: str = "primary") -> Optional[Dict[str, Any]]:
    """
    Retrieve a single event by its ID.

    Args:
        event_id: The event's unique identifier.
        calendar_id: Calendar ID (default: "primary").

    Returns:
        Event resource dictionary or None if not found.

    Raises:
        RuntimeError: If Calendar API is unavailable.
    """
    service = get_calendar_service()
    if not service:
        raise RuntimeError("Google Calendar API not available")

    try:
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        log.info(f"Fetched event {event_id}")
        return event
    except HttpError as e:
        if e.resp.status == 404:
            log.warning(f"Event {event_id} not found")
            return None
        log.error(f"API error getting event {event_id}: {e}")
        raise


def create_event(
    summary: str,
    start_time: Union[str, datetime],
    end_time: Union[str, datetime],
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[Dict[str, str]]] = None,
    calendar_id: str = "primary",
    recurrence: Optional[Union[str, List[str]]] = None,
    reminders: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a new calendar event.

    Args:
        summary: Event title/description.
        start_time: Start datetime (ISO string or datetime).
        end_time: End datetime (ISO string or datetime).
        description: Optional event description.
        location: Optional location string.
        attendees: Optional list of attendee dicts: [{"email": "...", "displayName": "..."}].
        calendar_id: Calendar ID (default: "primary").
        recurrence: Optional RRULE string or list of RRULE strings for recurring events.
        reminders: Optional reminder settings dict.

    Returns:
        The created event resource.

    Raises:
        RuntimeError: If Calendar API is unavailable.
        HttpError: On API failures (including conflicts).
    """
    service = get_calendar_service()
    if not service:
        raise RuntimeError("Google Calendar API not available")

    event_body: Dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": _parse_datetime(start_time)},
        "end": {"dateTime": _parse_datetime(end_time)},
    }

    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees:
        event_body["attendees"] = attendees
    if recurrence:
        if isinstance(recurrence, str):
            event_body["recurrence"] = [recurrence]
        else:
            event_body["recurrence"] = list(recurrence)
    if reminders:
        event_body["reminders"] = reminders

    # Validate: end time must be after start time
    start_dt = start_time if isinstance(start_time, datetime) else datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    end_dt = end_time if isinstance(end_time, datetime) else datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    if end_dt <= start_dt:
        raise ValueError("Event end time must be after start time")

    try:
        event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        log.info(f"Created event {event.get('id')}: {summary}")
        return event
    except HttpError as e:
        log.error(f"Failed to create event: {e}")
        raise


def update_event(
    event_id: str,
    calendar_id: str = "primary",
    **updates: Any,
) -> Dict[str, Any]:
    """
    Update an existing event. Only provided fields are updated.

    Args:
        event_id: The event's identifier.
        calendar_id: Calendar ID (default: "primary").
        **updates: Fields to update (summary, start, end, description, location, etc.)
                  Use same structure as create_event arguments.

    Returns:
        Updated event resource.

    Raises:
        RuntimeError: If Calendar API is unavailable.
        HttpError: On API failures.
    """
    service = get_calendar_service()
    if not service:
        raise RuntimeError("Google Calendar API not available")

    # First fetch the existing event
    try:
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as e:
        if e.resp.status == 404:
            raise ValueError(f"Event {event_id} not found") from e
        raise

    # Apply updates
    updateable_fields = {
        "summary", "start", "end", "description", "location",
        "attendees", "recurrence", "reminders"
    }
    for key, value in updates.items():
        if key not in updateable_fields:
            log.warning(f"Skip unknown update field: {key}")
            continue
        if key in ("start", "end") and value is not None:
            # These are objects: {"dateTime": "..."} or {"date": "..."} for all-day
            if isinstance(value, dict):
                event[key] = value
            else:
                # Assume datetime or ISO string
                event[key] = {"dateTime": _parse_datetime(value)}
        else:
            event[key] = value

    # If updating times, validate
    start = event.get("start", {}).get("dateTime")
    end = event.get("end", {}).get("dateTime")
    if start and end:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end_dt <= start_dt:
                raise ValueError("Event end time must be after start time")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid datetime format: {e}") from e

    try:
        updated_event = service.events().update(
            calendarId=calendar_id, eventId=event_id, body=event
        ).execute()
        log.info(f"Updated event {event_id}")
        return updated_event
    except HttpError as e:
        log.error(f"Failed to update event {event_id}: {e}")
        raise


def delete_event(event_id: str, calendar_id: str = "primary") -> bool:
    """
    Delete an event.

    Args:
        event_id: The event's identifier.
        calendar_id: Calendar ID (default: "primary").

    Returns:
        True if deleted, False if not found.

    Raises:
        RuntimeError: If Calendar API is unavailable.
        HttpError: On other API failures.
    """
    service = get_calendar_service()
    if not service:
        raise RuntimeError("Google Calendar API not available")

    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        log.info(f"Deleted event {event_id}")
        return True
    except HttpError as e:
        if e.resp.status == 404:
            log.warning(f"Event {event_id} not found — cannot delete")
            return False
        log.error(f"Failed to delete event {event_id}: {e}")
        raise
