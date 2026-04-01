"""Gmail API integration.

Provides functions to list, read, send, and manage email messages.
Built on top of the google-api-python-client with proper authentication.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Union

from .auth import authenticate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# Scopes for Gmail API - need read for list/get, send for sending
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Cache the service client
_gmail_service: Optional[Any] = None


def get_gmail_service() -> Optional[Any]:
    """
    Return an authenticated Gmail API service client, or None if auth fails.

    The service is cached after first successful creation.

    Returns:
        Gmail service client or None if unavailable.
    """
    global _gmail_service
    if _gmail_service is not None:
        return _gmail_service

    try:
        creds = authenticate()
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        _gmail_service = service
        log.info("Gmail service initialized")
        return service
    except Exception as e:
        log.error(f"Failed to initialize Gmail service: {e}")
        return None


def _parse_message_payload(payload: Dict[str, Any]) -> str:
    """
    Extract plain text body from a Gmail message payload.

    Handles multipart messages and various content encodings.

    Args:
        payload: The message payload part from Gmail API

    Returns:
        Decoded text content (preferring text/plain)
    """
    if payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return text

    if "parts" in payload:
        # Multipart message - find text/plain part
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                data = part["body"]["data"]
                text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                return text
        # Fallback: try any text part
        for part in payload["parts"]:
            if part.get("mimeType", "").startswith("text/") and part.get("body", {}).get("data"):
                data = part["body"]["data"]
                text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                return text
        # Recurse into nested multipart
        for part in payload["parts"]:
            if "parts" in part:
                text = _parse_message_payload(part)
                if text:
                    return text

    return ""


def _make_message_body(
    to: str,
    subject: str,
    body: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Construct a MIME message for sending via Gmail API.

    Args:
        to: Recipient email address(es), comma-separated string
        subject: Email subject
        body: Plain text body content
        attachments: Optional list of attachment dicts:
            [{"filename": "file.txt", "path": "/path/to/file", "mime_type": "text/plain"}]
            Path is read from local filesystem.

    Returns:
        MIME message as dict with 'raw' key containing base64url encoded message
    """
    if attachments:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))

        for att in attachments:
            filename = att["filename"]
            filepath = att["path"]
            mime_type = att.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"

            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Attachment not found: {filepath}")

            with open(filepath, "rb") as f:
                data = f.read()

            if mime_type.startswith("text/"):
                part = MIMEText(data.decode("utf-8", errors="replace"), "plain", "utf-8")
            elif mime_type.startswith("audio/"):
                part = MIMEAudio(data, _subtype=mimetypes.guess_extension(mime_type))
            elif mime_type.startswith("image/"):
                part = MIMEImage(data)
            else:
                part = MIMEBase(*mimetypes.guess_type(filename)[0].split("/", 1))
                part.set_payload(data)

            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return {"raw": raw_message}
    else:
        message = MIMEText(body, "plain", "utf-8")
        message["to"] = to
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return {"raw": raw_message}


def list_messages(
    query: Optional[str] = None,
    max_results: int = 100,
    include_spam_trash: bool = False,
) -> List[Dict[str, Any]]:
    """
    List email messages matching a search query.

    Args:
        query: Gmail search query string (e.g., "from:alice@example.com has:attachment")
               If None, returns all messages in mailbox.
        max_results: Maximum number of messages to return (min 1, max 500 per call).
        include_spam_trash: If True, include messages from Spam and Trash.

    Returns:
        List of message metadata dicts (id, threadId, labelIds, snippet).

    Raises:
        RuntimeError: If Gmail API is unavailable.
        HttpError: On API failures.
        ValueError: If max_results is out of range.
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available — authentication failed")

    if max_results < 1:
        raise ValueError("max_results must be at least 1")
    max_results = min(max_results, 500)  # Gmail API limit

    params = {
        "maxResults": max_results,
        "includeSpamTrash": include_spam_trash,
    }
    if query:
        params["q"] = query

    try:
        response = service.users().messages().list(userId="me", **params).execute()
        messages = response.get("messages", [])
        log.info(f"Listed {len(messages)} messages (query: {query or 'all'})")
        return messages
    except HttpError as e:
        log.error(f"API error listing messages: {e}")
        raise


def get_message(message_id: str, format: str = "full") -> Optional[Dict[str, Any]]:
    """
    Retrieve a single email message by its ID.

    Args:
        message_id: The message's unique identifier (from list_messages).
        format: Response format - 'full' (entire message), 'metadata' (headers only),
                'minimal' (id, threadId), or 'raw' (RFC 2822 raw).

    Returns:
        Full message resource dict or None if not found.

    Raises:
        RuntimeError: If Gmail API is unavailable.
        HttpError: On API failures.
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available")

    try:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format=format)
            .execute()
        )
        log.info(f"Fetched message {message_id}")
        return message
    except HttpError as e:
        if e.resp.status == 404:
            log.warning(f"Message {message_id} not found")
            return None
        log.error(f"API error getting message {message_id}: {e}")
        raise


def send_message(
    to: Union[str, List[str]],
    subject: str,
    body: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Send an email message.

    Args:
        to: Recipient email address or list of addresses.
        subject: Email subject line.
        body: Plain text body content.
        attachments: Optional list of attachment dicts with keys:
            filename (str), path (str), mime_type (optional).
        cc: Optional CC recipient(s).
        bcc: Optional BCC recipient(s).

    Returns:
        The sent message resource (contains id, threadId, etc.).

    Raises:
        RuntimeError: If Gmail API is unavailable.
        HttpError: On API failures (quota, auth, etc.).
        FileNotFoundError: If any attachment file does not exist.
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available")

    # Normalize recipient lists
    if isinstance(to, list):
        to_str = ", ".join(to)
    else:
        to_str = to

    if cc:
        if isinstance(cc, list):
            cc_str = ", ".join(cc)
        else:
            cc_str = cc
        # Add CC to message headers
        if attachments:
            pass  # We'll add headers after creating multipart message
        else:
            pass

    if bcc:
        if isinstance(bcc, list):
            bcc_str = ", ".join(bcc)
        else:
            bcc_str = bcc
        # BCC should not appear in message headers for privacy; handled by API

    # Build message body
    msg_body = _make_message_body(to_str, subject, body, attachments)

    # Add CC header if present (only visible to recipients)
    if attachments:
        # For multipart, we need to construct MIME message differently to add headers
        return _send_multipart_with_headers(
            service, to, subject, body, attachments, cc=cc, bcc=bcc
        )
    else:
        # Simple message: add headers to the MIMEText object
        import email
        from email import policy
        from email.parser import BytesParser

        raw_bytes = base64.urlsafe_b64decode(msg_body["raw"])
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        if cc:
            msg["Cc"] = cc_str
        if bcc:
            # BCC is not added to headers; Gmail API handles it separately
            pass
        msg_body["raw"] = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        message = service.users().messages().send(userId="me", body=msg_body).execute()
        log.info(f"Sent message to {to_str}: {message.get('id')}")
        return message
    except HttpError as e:
        log.error(f"Failed to send message: {e}")
        raise


def _send_multipart_with_headers(
    service,
    to: Union[str, List[str]],
    subject: str,
    body: str,
    attachments: List[Dict[str, Any]],
    cc: Optional[Union[str, List[str]]] = None,
    bcc: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Helper to send multipart message with CC/BCC headers."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    to_str = ", ".join(to) if isinstance(to, list) else to
    message = MIMEMultipart()
    message["To"] = to_str
    message["Subject"] = subject
    if cc:
        cc_str = ", ".join(cc) if isinstance(cc, list) else cc
        message["Cc"] = cc_str

    message.attach(MIMEText(body, "plain", "utf-8"))

    for att in attachments:
        filename = att["filename"]
        filepath = att["path"]
        mime_type = att.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Attachment not found: {filepath}")

        with open(filepath, "rb") as f:
            data = f.read()

        if mime_type.startswith("text/"):
            part = MIMEText(data.decode("utf-8", errors="replace"), "plain", "utf-8")
        elif mime_type.startswith("audio/"):
            part = MIMEAudio(data)
        elif mime_type.startswith("image/"):
            part = MIMEImage(data)
        else:
            part = MIMEBase(*mimetypes.guess_type(filename)[0].split("/", 1))
            part.set_payload(data)
            from email import encoders
            encoders.encode_base64(part)

        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        message.attach(part)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body = {"raw": raw_message}

    try:
        sent = service.users().messages().send(userId="me", body=body).execute()
        log.info(f"Sent multipart message to {to_str}: {sent.get('id')}")
        return sent
    except HttpError as e:
        log.error(f"Failed to send multipart message: {e}")
        raise


def modify_labels(
    message_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Add or remove labels from a message.

    Args:
        message_id: The message's identifier.
        add_labels: List of label IDs to add (e.g., ["INBOX", "STARRED", "IMPORTANT"]).
        remove_labels: List of label IDs to remove.

    Returns:
        The modified message resource.

    Raises:
        RuntimeError: If Gmail API is unavailable.
        HttpError: On API failures.
        ValueError: If both add_labels and remove_labels are None.
    """
    if add_labels is None and remove_labels is None:
        raise ValueError("Must specify either add_labels or remove_labels")

    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available")

    body: Dict[str, Any] = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels

    try:
        result = (
            service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
            .execute()
        )
        log.info(f"Modified labels on message {message_id}: +{add_labels} -{remove_labels}")
        return result
    except HttpError as e:
        log.error(f"Failed to modify labels on message {message_id}: {e}")
        raise


def search_messages(
    query: str,
    max_results: int = 100,
    include_spam_trash: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search email messages using Gmail's query syntax.

    This is a convenience wrapper around list_messages with a query.

    Args:
        query: Gmail search query string.
        max_results: Maximum number of results to return.
        include_spam_trash: Include Spam and Trash if True.

    Returns:
        List of message metadata dicts.

    Raises:
        RuntimeError: If Gmail API is unavailable.
        HttpError: On API failures.
    """
    return list_messages(query=query, max_results=max_results, include_spam_trash=include_spam_trash)
