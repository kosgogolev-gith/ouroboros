"""Drive API tools: list_files, read_file, write_file, delete_file."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.utils import utc_now_iso, append_jsonl, truncate_for_log

log = logging.getLogger(__name__)

# Import from the new integrations module
try:
    from ouroboros.integrations.google.auth import get_credentials
    from ouroboros.integrations.google.drive import DriveClient, FileNotFoundError, DriveError
    INTEGRATIONS_AVAILABLE = True
except ImportError as e:
    log.warning("Google integrations not available: %s", e)
    INTEGRATIONS_AVAILABLE = False


# --- Retry logic ---

def _retry_with_backoff(func, max_attempts: int = 3, initial_delay: float = 1.0):
    """Retry with exponential backoff for quota errors."""
    delay = initial_delay
    last_exception = None
    for attempt in range(max_attempts):
        try:
            return func()
        except DriveError as e:
            if "quota" in str(e).lower() or "rate limit" in str(e).lower():
                last_exception = e
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            else:
                raise
        except Exception as e:
            raise
    if last_exception:
        raise last_exception


# --- Helper: get Drive client ---

def _get_drive_client(ctx: ToolContext) -> DriveClient:
    """Get authenticated Drive client, or raise if unavailable."""
    if not INTEGRATIONS_AVAILABLE:
        raise RuntimeError("Google integrations not installed or failed to import")
    creds = get_credentials()
    return DriveClient(creds)


# --- Tool implementations ---

def _list_files(ctx: ToolContext, path: str = "root") -> str:
    """List files and folders in a Drive directory."""
    try:
        client = _get_drive_client(ctx)
        result = _retry_with_backoff(lambda: client.list_files(path))
        if not result:
            return f"Directory '{path}' is empty or not found."
        # Format output
        lines = [f"📁 {path}:"]
        for item in result:
            icon = "📁" if item['mimeType'] == 'application/vnd.google-apps.folder' else "📄"
            lines.append(f"  {icon} {item['name']} (id: {item['id']}, mime: {item['mimeType']})")
        return "\n".join(lines)
    except FileNotFoundError as e:
        return f"⚠️ NOT_FOUND: {e}"
    except DriveError as e:
        return f"⚠️ DRIVE_ERROR: {e}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _read_file(ctx: ToolContext, path: str) -> str:
    """Read a file from Drive by path (filename or id). Returns text content."""
    try:
        client = _get_drive_client(ctx)
        content = _retry_with_backoff(lambda: client.read_file(path))
        return content
    except FileNotFoundError as e:
        return f"⚠️ NOT_FOUND: {e}"
    except DriveError as e:
        return f"⚠️ DRIVE_ERROR: {e}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _write_file(ctx: ToolContext, path: str, content: str, mode: str = "overwrite") -> str:
    """
    Write content to a file on Drive.
    mode: 'overwrite' (default) or 'append'
    """
    if mode not in ("overwrite", "append"):
        return "⚠️ ERROR: mode must be 'overwrite' or 'append'"
    try:
        client = _get_drive_client(ctx)
        # Determine mime type based on extension (simple heuristics)
        mime_type = "text/plain;charset=utf-8"
        if path.endswith(".md"):
            mime_type = "text/markdown"
        elif path.endswith(".json"):
            mime_type = "application/json"
        elif path.endswith(".py"):
            mime_type = "text/x-python"
        elif path.endswith(".html"):
            mime_type = "text/html"
        elif path.endswith(".csv"):
            mime_type = "text/csv"
        # For append mode, we need to read existing content first
        if mode == "append":
            try:
                existing = client.read_file(path)
                content = existing + content
            except FileNotFoundError:
                pass  # If file doesn't exist, append becomes create
        operation = "updated" if mode == "overwrite" else "appended to"
        result = _retry_with_backoff(lambda: client.write_file(path, content, mime_type=mime_type))
        return f"OK: {operation} '{path}' ({len(content)} bytes, mime: {mime_type})"
    except DriveError as e:
        return f"⚠️ DRIVE_ERROR: {e}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _delete_file(ctx: ToolContext, path: str) -> str:
    """Delete a file or folder from Drive by path or id."""
    try:
        client = _get_drive_client(ctx)
        result = _retry_with_backoff(lambda: client.delete_file(path))
        if result:
            return f"OK: deleted '{path}'"
        else:
            return f"⚠️ NOT_FOUND: '{path}' not found"
    except DriveError as e:
        return f"⚠️ DRIVE_ERROR: {e}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("drive_list", {
            "name": "drive_list",
            "description": "List files and folders in Google Drive. Path can be folder name or 'root'.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "default": "root", "description": "Folder path or name to list (default: root)"},
            }, "required": []},
        }, _list_files),
        ToolEntry("drive_read", {
            "name": "drive_read",
            "description": "Read a file from Google Drive by path (filename or id). Returns text content.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "File path (relative to Drive root) or file ID"},
            }, "required": ["path"]},
        }, _read_file),
        ToolEntry("drive_write", {
            "name": "drive_write",
            "description": "Write content to a file on Google Drive. Supports 'overwrite' and 'append' modes. Auto-detects MIME type from extension.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "File path (relative to Drive root) or file ID"},
                "content": {"type": "string", "description": "Text content to write"},
                "mode": {"type": "string", "enum": ["overwrite", "append"], "default": "overwrite", "description": "Write mode"},
            }, "required": ["path", "content"]},
        }, _write_file),
        ToolEntry("drive_delete", {
            "name": "drive_delete",
            "description": "Delete a file or folder from Google Drive by path or id.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "File path (relative to Drive root) or file ID"},
            }, "required": ["path"]},
        }, _delete_file),
    ]
