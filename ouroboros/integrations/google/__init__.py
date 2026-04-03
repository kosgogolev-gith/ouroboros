"""Google API integrations package.

Provides unified access to Google services:
- auth: Authentication client (Colab + OAuth file fallback)
- drive: Google Drive file operations
- calendar: Google Calendar event management
- gmail: Gmail email operations
"""

from .auth import get_credentials
from .drive import (
    list_files,
    read_file,
    write_file,
    delete_file,
)
from .calendar import (
    get_calendar_service,
    list_events,
    get_event,
    create_event,
    update_event,
    delete_event,
)
from .gmail import (
    get_gmail_service,
    list_messages,
    get_message,
    send_message,
    modify_labels,
    search_messages,
)

__all__ = [
    # Auth
    "get_credentials",
    # Drive
    "list_files",
    "read_file",
    "write_file",
    "delete_file",
    # Calendar
    "get_calendar_service",
    "list_events",
    "get_event",
    "create_event",
    "update_event",
    "delete_event",
    # Gmail
    "get_gmail_service",
    "list_messages",
    "get_message",
    "send_message",
    "modify_labels",
    "search_messages",
]