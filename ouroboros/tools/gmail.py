"""Gmail API tools: list_messages, get_message, send_message, modify_labels, search_messages."""

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
    from ouroboros.integrations.google.gmail import (
        get_gmail_service,
        list_messages,
        get_message,
        send_message,
        modify_labels,
        search_messages,
    )
    INTEGRATIONS_AVAILABLE = True
except ImportError as e:
    log.warning("Google Gmail integrations not available: %s", e)
    INTEGRATIONS_AVAILABLE = False


# --- Retry logic ---

def _retry_with_backoff(func, max_attempts: int = 3, initial_delay: float = 1.0):
    """Retry with exponential backoff for quota errors."""
    delay = initial_delay
    last_exception = None
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            # Generic retry on any exception (conservative)
            last_exception = e
            if attempt < max_attempts - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    if last_exception:
        raise last_exception


# --- Helper: get Gmail client service ---

def _get_gmail_service(ctx: ToolContext):
    """Get authenticated Gmail service, or raise if unavailable."""
    if not INTEGRATIONS_AVAILABLE:
        raise RuntimeError("Gmail integrations not installed or failed to import")
    return get_gmail_service()  # Already cached internally


# --- Tool implementations ---

def _list_messages(
    ctx: ToolContext,
    query: Optional[str] = None,
    max_results: int = 100,
    include_spam_trash: bool = False,
) -> str:
    """List email messages matching a search query."""
    try:
        service = _get_gmail_service(ctx)
        result = _retry_with_backoff(
            lambda: list_messages(query=query, max_results=max_results, include_spam_trash=include_spam_trash)
        )
        if not result:
            return "No messages found matching the query."
        lines = [f"📧 Found {len(result)} messages:"]
        for msg in result:
            lines.append(f"  ID: {msg.get('id')}, Thread: {msg.get('threadId')}, Labels: {msg.get('labelIds', [])}")
            snippet = msg.get('snippet', '')
            if snippet:
                lines.append(f"    Snippet: {snippet[:100]}{'...' if len(snippet) > 100 else ''}")
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _get_message(ctx: ToolContext, message_id: str, format: str = "full") -> str:
    """Retrieve a single email message by its ID."""
    try:
        service = _get_gmail_service(ctx)
        msg = _retry_with_backoff(lambda: get_message(message_id, format=format))
        if msg is None:
            return f"Message {message_id} not found."
        # Extract useful info
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
        to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
        labels = msg.get('labelIds', [])
        snippet = msg.get('snippet', '')
        body = _extract_body_from_message(msg)

        lines = [
            f"✉️ Message {message_id}:",
            f"  From: {sender}",
            f"  To: {to}",
            f"  Subject: {subject}",
            f"  Date: {date}",
            f"  Labels: {', '.join(labels)}",
            f"  Snippet: {snippet[:200]}{'...' if len(snippet) > 200 else ''}",
        ]
        if body:
            lines.append("  Body (plain text):")
            lines.append("    " + body[:500].replace("\n", "\n    "))
            if len(body) > 500:
                lines.append("    ... (truncated)")
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _extract_body_from_message(msg: Dict[str, Any]) -> str:
    """Extract plain text body from a Gmail message dict (similar to internal helper)."""
    payload = msg.get('payload', {})
    if payload.get('body', {}).get('data'):
        import base64
        data = payload['body']['data']
        text = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        return text

    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                import base64
                data = part['body']['data']
                text = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                return text
        # Fallback: any text part
        for part in payload['parts']:
            if part.get('mimeType', '').startswith('text/') and part.get('body', {}).get('data'):
                import base64
                data = part['body']['data']
                text = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                return text
        # Recurse into nested multipart
        for part in payload['parts']:
            if 'parts' in part:
                text = _extract_body_from_message({'payload': part})
                if text:
                    return text
    return ""


def _send_message(
    ctx: ToolContext,
    to: str,
    subject: str,
    body: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> str:
    """Send an email message."""
    try:
        service = _get_gmail_service(ctx)
        # Parse attachment list if provided
        att_list = None
        if attachments:
            att_list = []
            for att in attachments:
                # Expected: {"filename": "...", "path": "...", "mime_type": "..."}
                if not isinstance(att, dict) or 'filename' not in att or 'path' not in att:
                    return "⚠️ ERROR: each attachment must have 'filename' and 'path' keys"
                att_list.append(att)

        result = _retry_with_backoff(
            lambda: send_message(
                to=to,
                subject=subject,
                body=body,
                attachments=att_list,
                cc=cc,
                bcc=bcc,
            )
        )
        msg_id = result.get('id', 'unknown')
        thread_id = result.get('threadId', 'unknown')
        return f"✅ Message sent: id={msg_id}, threadId={thread_id}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _modify_labels(
    ctx: ToolContext,
    message_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> str:
    """Add or remove labels from a message."""
    if add_labels is None and remove_labels is None:
        return "⚠️ ERROR: Must specify either add_labels or remove_labels"
    try:
        service = _get_gmail_service(ctx)
        result = _retry_with_backoff(
            lambda: modify_labels(
                message_id=message_id,
                add_labels=add_labels,
                remove_labels=remove_labels,
            )
        )
        new_labels = result.get('labelIds', [])
        return f"✅ Modified labels on message {message_id}. New labels: {', '.join(new_labels)}"
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def _search_messages(
    ctx: ToolContext,
    query: str,
    max_results: int = 100,
    include_spam_trash: bool = False,
) -> str:
    """Search email messages using Gmail's query syntax."""
    try:
        service = _get_gmail_service(ctx)
        result = _retry_with_backoff(
            lambda: search_messages(
                query=query,
                max_results=max_results,
                include_spam_trash=include_spam_trash,
            )
        )
        if not result:
            return f"No messages found for query: {query}"
        lines = [f"🔍 Found {len(result)} messages for '{query}':"]
        for msg in result:
            lines.append(f"  ID: {msg.get('id')}, Thread: {msg.get('threadId')}, Labels: {msg.get('labelIds', [])}")
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ ERROR: {type(e).__name__}: {e}"


def get_tools() -> List[ToolEntry]:
    """Return Gmail tool entries for the registry."""
    return [
        ToolEntry("gmail_list", {
            "name": "gmail_list",
            "description": "List email messages matching a search query. Returns message metadata (id, threadId, labels, snippet).",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Gmail search query (e.g., 'from:alice@example.com has:attachment')"},
                "max_results": {"type": "integer", "default": 100, "description": "Maximum number of messages to return (1-500)"},
                "include_spam_trash": {"type": "boolean", "default": False, "description": "Include Spam and Trash folders"},
            }, "required": []},
        }, _list_messages),
        ToolEntry("gmail_get", {
            "name": "gmail_get",
            "description": "Retrieve a single email message by ID. Returns headers, body, labels, and metadata.",
            "parameters": {"type": "object", "properties": {
                "message_id": {"type": "string", "description": "The message's unique identifier (from gmail_list)"},
                "format": {"type": "string", "enum": ["full", "metadata", "minimal", "raw"], "default": "full", "description": "Response format"},
            }, "required": ["message_id"]},
        }, _get_message),
        ToolEntry("gmail_send", {
            "name": "gmail_send",
            "description": "Send an email message. Supports plain text body and optional attachments.",
            "parameters": {"type": "object", "properties": {
                "to": {"type": "string", "description": "Recipient email address or comma-separated list"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Plain text body content"},
                "attachments": {"type": "array", "items": {"type": "object", "properties": {
                    "filename": {"type": "string"},
                    "path": {"type": "string"},
                    "mime_type": {"type": "string"}
                }}, "description": "Optional list of attachments with filename, local path, and optional MIME type"},
                "cc": {"type": "string", "description": "CC recipient(s), comma-separated"},
                "bcc": {"type": "string", "description": "BCC recipient(s), comma-separated (not shown in headers)"},
            }, "required": ["to", "subject", "body"]},
        }, _send_message),
        ToolEntry("gmail_modify_labels", {
            "name": "gmail_modify_labels",
            "description": "Add or remove labels from a message. Label IDs are like 'INBOX', 'STARRED', 'IMPORTANT', 'CATEGORY_PROMOTIONS', etc.",
            "parameters": {"type": "object", "properties": {
                "message_id": {"type": "string", "description": "The message's identifier"},
                "add_labels": {"type": "array", "items": {"type": "string"}, "description": "List of label IDs to add"},
                "remove_labels": {"type": "array", "items": {"type": "string"}, "description": "List of label IDs to remove"},
            }, "required": ["message_id"]},
        }, _modify_labels),
        ToolEntry("gmail_search", {
            "name": "gmail_search",
            "description": "Search email messages using Gmail's query syntax (same as gmail_list but with query required).",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Gmail search query (required)"},
                "max_results": {"type": "integer", "default": 100, "description": "Maximum number of results (1-500)"},
                "include_spam_trash": {"type": "boolean", "default": False, "description": "Include Spam and Trash folders"},
            }, "required": ["query"]},
        }, _search_messages),
    ]
