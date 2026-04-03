"""Drive API tools: list_files, read_file, write_file, delete_file."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# Import from the new integrations module
try:
    from ouroboros.integrations.google.drive import (
        list_files as drive_list_files,
        read_file as drive_read_file,
        write_file as drive_write_file,
        delete_file as drive_delete_file,
    )
    INTEGRATIONS_AVAILABLE = True
except ImportError as e:
    log.warning("Google integrations not available: %s", e)
    INTEGRATIONS_AVAILABLE = False


def _check_available() -> None:
    """Raise if Google integrations are not available."""
    if not INTEGRATIONS_AVAILABLE:
        raise RuntimeError("Google integrations not installed or failed to import")


# --- Tool implementations ---

def _list_files(ctx: ToolContext, path: str = "root") -> str:
    """List files and folders in a Drive directory."""
    try:
        _check_available()
        result = drive_list_files(path)
        if not result:
            return f"Directory '{path}' is empty or not found."
        lines = [f"📁 {path}:"]
        for item in result:
            icon = "📁" if item['mimeType'] == 'application/vnd.google-apps.folder' else "📄"
            lines.append(f"  {icon} {item['name']} (id: {item['id']}, mime: {item['mimeType']})")
        return "\n".join(lines)
    except FileNotFoundError as e:
        return f"⚠️ NOT_FOUND: {e}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _read_file(ctx: ToolContext, path: str) -> str:
    """Read a file from Drive by path (filename or id). Returns text content."""
    try:
        _check_available()
        return drive_read_file(path)
    except FileNotFoundError as e:
        return f"⚠️ NOT_FOUND: {e}"
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
        _check_available()
        result = drive_write_file(path, content, mode=mode)
        operation = "updated" if mode == "overwrite" else "appended to"
        return f"OK: {operation} '{path}' ({len(content)} bytes)"
    except FileNotFoundError as e:
        return f"⚠️ NOT_FOUND: {e}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _delete_file(ctx: ToolContext, path: str) -> str:
    """Delete a file or folder from Drive by path or id."""
    try:
        _check_available()
        result = drive_delete_file(path)
        if result:
            return f"OK: deleted '{path}'"
        else:
            return f"⚠️ NOT_FOUND: '{path}' not found"
    except FileNotFoundError as e:
        return f"⚠️ NOT_FOUND: {e}"
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
