"""Google API integration via OAuth 2.0.

Provides authenticated clients for Drive, Gmail, Calendar using user credentials.
Falls back to file-based operations if credentials not available or auth fails.
"""

from __future__ import annotations

import base64
import email
import logging
import os
import pathlib
import tempfile
import time
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, List, Optional, Dict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

log = logging.getLogger(__name__)

# Scopes for various Google services
SCOPES_DRIVE = ["https://www.googleapis.com/auth/drive.file"]
SCOPES_GMAIL_READ = ["https://www.googleapis.com/auth/gmail.readonly"]
SCOPES_GMAIL_SEND = ["https://www.googleapis.com/auth/gmail.send"]
SCOPES_GMAIL = SCOPES_GMAIL_READ + SCOPES_GMAIL_SEND
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar.readonly"]

def _load_credentials(credentials_path: str, scopes: List[str]) -> Optional[Credentials]:
    """Load OAuth 2.0 credentials from file, refresh if needed."""
    if not os.path.exists(credentials_path):
        log.warning(f"Credentials file not found: {credentials_path}")
        return None
    try:
        creds = Credentials.from_authorized_user_file(credentials_path, scopes)
    except Exception as e:
        log.error(f"Failed to load credentials: {e}")
        return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed credentials back to file
            with open(credentials_path, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            log.error(f"Failed to refresh credentials: {e}")
            return None
    return creds

_drive_service_cache: Optional[Any] = None
_gmail_service_cache: Optional[Any] = None
_calendar_service_cache: Optional[Any] = None

def get_drive_service() -> Optional[Any]:
    """Return an authenticated Drive API service client, or None if not available."""
    global _drive_service_cache
    if _drive_service_cache is not None:
        return _drive_service_cache
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        log.info("GOOGLE_CREDENTIALS_PATH not set — Google API disabled")
        return None
    creds = _load_credentials(creds_path, SCOPES_DRIVE)
    if not creds:
        log.warning("Failed to obtain Google credentials for Drive — API disabled")
        return None
    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        _drive_service_cache = service
        return service
    except HttpError as e:
        log.error(f"Failed to build Drive service: {e}")
        return None

def get_gmail_service() -> Optional[Any]:
    """Return an authenticated Gmail API service client, or None if not available."""
    global _gmail_service_cache
    if _gmail_service_cache is not None:
        return _gmail_service_cache
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        log.info("GOOGLE_CREDENTIALS_PATH not set — Gmail API disabled")
        return None
    creds = _load_credentials(creds_path, SCOPES_GMAIL)
    if not creds:
        log.warning("Failed to obtain Google credentials for Gmail — API disabled")
        return None
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        _gmail_service_cache = service
        return service
    except HttpError as e:
        log.error(f"Failed to build Gmail service: {e}")
        return None

def get_calendar_service() -> Optional[Any]:
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        return None
    creds = _load_credentials(creds_path, SCOPES_CALENDAR)
    if not creds:
        return None
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        _calendar_service_cache = service
        return service
    except HttpError as e:
        log.error(f"Failed to build Calendar service: {e}")
        return None

# ===================== Gmail API Implementation =====================

def list_messages(query: str = "", max_results: int = 100) -> List[Dict[str, Any]]:
    """
    List Gmail messages matching a query.

    Args:
        query: Gmail search query (e.g., 'from:alice@example.com', 'subject:meeting')
        max_results: Maximum number of messages to return (default 100)

    Returns:
        List of message dicts with id, threadId, snippet, and internalDate.
        Raises RuntimeError if Gmail API not available.
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available — check GOOGLE_CREDENTIALS_PATH")

    messages = []
    try:
        response = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        batch = response.get('messages', [])
        messages.extend(batch)

        # Handle pagination
        while 'nextPageToken' in response and len(messages) < max_results:
            page_token = response['nextPageToken']
            response = service.users().messages().list(userId='me', q=query, maxResults=max_results, pageToken=page_token).execute()
            batch = response.get('messages', [])
            messages.extend(batch)

        # Truncate to max_results
        messages = messages[:max_results]
    except HttpError as e:
        log.error(f"Gmail list_messages failed: {e}")
        raise RuntimeError(f"Gmail API error: {e}")
    except Exception as e:
        log.error(f"Unexpected error in list_messages: {e}")
        raise

    return messages

def get_message(message_id: str) -> Dict[str, Any]:
    """
    Retrieve full message details including headers, body, and attachment metadata.

    Args:
        message_id: Gmail message ID

    Returns:
        Dict with keys:
        - headers: dict of header name -> value
        - body: text body (plain or HTML, whichever is present; prefers plain)
        - html_body: HTML body if present
        - attachments: list of dicts {id, filename, mimeType, size}
        - raw: raw RFC 822 message (base64url encoded)
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available")

    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    except HttpError as e:
        log.error(f"Gmail get_message failed for {message_id}: {e}")
        raise RuntimeError(f"Failed to get message {message_id}: {e}")

    # Parse headers
    headers = {}
    for h in msg['payload'].get('headers', []):
        headers[h['name']] = h['value']

    # Decode payload to extract body and attachments
    body = ""
    html_body = ""
    attachments = []
    raw_payload = msg.get('raw', '')

    def _parse_part(part: Dict[str, Any]) -> None:
        nonlocal body, html_body
        mime_type = part.get('mimeType', '')
        data = part.get('body', {}).get('data')
        if data:
            # Data is base64url encoded
            try:
                decoded = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='replace')
            except Exception as e:
                decoded = ""
            if mime_type == 'text/plain' and not body:
                body = decoded
            elif mime_type == 'text/html' and not html_body:
                html_body = decoded
        # Attachment?
        if part.get('filename') and part.get('body', {}).get('attachmentId'):
            attachments.append({
                'id': part['body']['attachmentId'],
                'filename': part['filename'],
                'mimeType': mime_type,
                'size': part['body'].get('size', 0)
            })
        # Recurse into multipart
        if 'parts' in part:
            for sub in part['parts']:
                _parse_part(sub)

    _parse_part(msg['payload'])

    return {
        'id': message_id,
        'threadId': msg.get('threadId'),
        'snippet': msg.get('snippet', ''),
        'internalDate': msg.get('internalDate'),
        'headers': headers,
        'body': body,
        'html_body': html_body,
        'attachments': attachments,
        'raw': raw_payload,
    }

def send_message(to: str, subject: str, body: str, html_body: Optional[str] = None, attachments: Optional[List[str]] = None) -> str:
    """
    Send an email via Gmail.

    Args:
        to: Recipient email address (or comma-separated list)
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML version (if provided, message becomes multipart/alternative)
        attachments: List of file paths to attach

    Returns:
        The sent message ID.
    Raises:
        RuntimeError if Gmail API not available or send fails.
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available")

    if attachments:
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        # Alternatives part for text + HTML if both provided
        if html_body:
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText(body, 'plain', 'utf-8'))
            alt.attach(MIMEText(html_body, 'html', 'utf-8'))
            message.attach(alt)
        else:
            message.attach(MIMEText(body, 'plain', 'utf-8'))
        # Attach files
        for file_path in attachments:
            if not os.path.isfile(file_path):
                log.warning(f"Attachment not found: {file_path} — skipping")
                continue
            filename = os.path.basename(file_path)
            # Guess mime type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            main_type, sub_type = mime_type.split('/', 1)
            with open(file_path, 'rb') as f:
                file_data = f.read()
            if main_type == 'text':
                attachment = MIMEText(file_data.decode('utf-8', errors='replace'), _subtype=sub_type)
            elif main_type == 'image':
                attachment = MIMEImage(file_data, _subtype=sub_type)
            elif main_type == 'audio':
                attachment = MIMEAudio(file_data, _subtype=sub_type)
            else:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(file_data)
                from email import encoders
                encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            message.attach(attachment)
    else:
        # No attachments: simple message or multipart/alternative if HTML provided
        if html_body:
            message = MIMEMultipart('alternative')
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain', 'utf-8'))
            message.attach(MIMEText(html_body, 'html', 'utf-8'))
        else:
            message = MIMEText(body, 'plain', 'utf-8')
            message['to'] = to
            message['subject'] = subject

    # Encode message to base64url
    raw_bytes = message.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode('ASCII')

    try:
        sent = service.users().messages().send(userId='me', body={'raw': raw_b64}).execute()
        return sent['id']
    except HttpError as e:
        log.error(f"Gmail send_message failed: {e}")
        raise RuntimeError(f"Failed to send message: {e}")

def download_attachment(message_id: str, attachment_id: str, save_path: Optional[str] = None) -> bytes:
    """
    Download an attachment from a message.

    Args:
        message_id: Gmail message ID
        attachment_id: Attachment ID from get_message()
        save_path: Optional file path to save to. If None, returns bytes.

    Returns:
        bytes of the attachment, or raises.
    """
    service = get_gmail_service()
    if not service:
        raise RuntimeError("Gmail API not available")

    try:
        att = service.users().messages().attachments().get(userId='me', messageId=message_id, id=attachment_id).execute()
        data = att.get('data', '')
        file_bytes = base64.urlsafe_b64decode(data.encode('ASCII'))
        if save_path:
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
            log.info(f"Saved attachment to {save_path}")
        return file_bytes
    except HttpError as e:
        log.error(f"Failed to download attachment {attachment_id} from {message_id}: {e}")
        raise RuntimeError(f"Attachment download failed: {e}")

# ===================== Helper Functions =====================

def search_by_sender(sender_email: str, query: str = "", max_results: int = 100) -> List[Dict[str, Any]]:
    """Convenience wrapper: find messages from a specific sender, optionally combined with extra query."""
    full_query = f"from:{sender_email}"
    if query:
        full_query += f" {query}"
    return list_messages(full_query, max_results=max_results)

def search_by_subject(subject: str, query: str = "", max_results: int = 100) -> List[Dict[str, Any]]:
    """Convenience wrapper: find messages with subject containing given string, optionally combined."""
    full_query = f"subject:{subject}"
    if query:
        full_query += f" {query}"
    return list_messages(full_query, max_results=max_results)

def search_by_label(label: str, query: str = "", max_results: int = 100) -> List[Dict[str, Any]]:
    """Convenience wrapper: find messages with a specific Gmail label."""
    full_query = f"label:{label}"
    if query:
        full_query += f" {query}"
    return list_messages(full_query, max_results=max_results)

def get_gmail_service_info() -> Dict[str, Any]:
    """Return info about Gmail service status (for debugging)."""
    service = get_gmail_service()
    if not service:
        return {"available": False, "reason": "Credentials not found or invalid"}
    try:
        profile = service.users().getProfile(userId='me').execute()
        return {
            "available": True,
            "email_address": profile.get('emailAddress'),
            "messages_total": profile.get('messagesTotal'),
            "threads_total": profile.get('threadsTotal'),
        }
    except HttpError as e:
        return {"available": False, "reason": f"HTTP error: {e}"}
    except Exception as e:
        return {"available": False, "reason": f"Unexpected: {e}"}

# ===================== Drive and Calendar remain as before =====================

def drive_list_api(remote_folder_path: str = "root") -> List[str]:
    """List files in a Drive folder via API. Returns list of file names (strings)."""
    service = get_drive_service()
    if not service:
        raise RuntimeError("Google Drive API not available")
    # Resolve folder ID
    if remote_folder_path == "root":
        folder_id = "root"
    else:
        # Find folder by path (drive has no real directories — use title and parents)
        parts = remote_folder_path.strip("/").split("/")
        parent_id = "root"
        for part in parts:
            query = f"name='{part}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
            res = service.files().list(q=query, fields="files(id, name)").execute()
            files = res.get("files", [])
            if not files:
                raise FileNotFoundError(f"Folder not found in Drive: {part}")
            parent_id = files[0]["id"]
        folder_id = parent_id
    # List files in folder
    res = service.files().list(q=f"'{folder_id}' in parents and trashed=false", fields="files(id, name)").execute()
    names = [f["name"] for f in res.get("files", [])]
    return names

def drive_read_api(file_path: str) -> str:
    """Read a text file from Drive by its path (relative to MyDrive/Ouroboros)."""
    service = get_drive_service()
    if not service:
        raise RuntimeError("Google Drive API not available")
    # Resolve file ID by path
    parts = file_path.strip("/").split("/")
    parent_id = "root"
    for i, part in enumerate(parts):
        is_last = (i == len(parts) - 1)
        mime_type = "application/vnd.google-apps.folder" if not is_last else None
        query_parts = [f"name='{part}'", f"'{parent_id}' in parents", "trashed=false"]
        if mime_type:
            query_parts.append(f"mimeType='{mime_type}'")
        query = " and ".join(query_parts)
        res = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        files = res.get("files", [])
        if not files:
            raise FileNotFoundError(f"Path component not found in Drive: {part}")
        if is_last:
            file_id = files[0]["id"]
            mime = files[0].get("mimeType", "")
            if mime != "text/plain":
                # Try to download as text anyway
                pass
            # Download file content
            from io import BytesIO
            request = service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            content_bytes = fh.getvalue()
            try:
                return content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return content_bytes.decode("utf-8", errors="replace")
        else:
            parent_id = files[0]["id"]

def drive_write_api(file_path: str, content: str, mode: str = "overwrite") -> str:
    """Write a text file to Drive via API."""
    service = get_drive_service()
    if not service:
        raise RuntimeError("Google Drive API not available")
    # Resolve parent folder ID
    parts = file_path.strip("/").split("/")
    filename = parts[-1]
    parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
    parent_id = "root"
    if parent_path:
        parent_parts = parent_path.split("/")
        for part in parent_parts:
            query = f"name='{part}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
            res = service.files().list(q=query, fields="files(id, name)").execute()
            files = res.get("files", [])
            if not files:
                # Create folder
                folder_metadata = {"name": part, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
                folder = service.files().create(body=folder_metadata, fields="id").execute()
                parent_id = folder["id"]
            else:
                parent_id = files[0]["id"]
    # Check if file already exists
    query = f"name='{filename}' and '{parent_id}' in parents and trashed=false"
    res = service.files().list(q=query, fields="files(id, name)").execute()
    existing = res.get("files", [])
    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt")
    tmp_path = tmp.name
    tmp.write(content)
    tmp.close()
    try:
        if existing and mode == "overwrite":
            file_id = existing[0]["id"]
            media_body = MediaFileUpload(tmp_path, mimetype="text/plain")
            service.files().update(fileId=file_id, media_body=media_body).execute()
            msg = f"Updated file {file_path} via API"
        else:
            file_metadata = {"name": filename, "parents": [parent_id]}
            media_body = MediaFileUpload(tmp_path, mimetype="text/plain")
            service.files().create(body=file_metadata, media_body=media_body).execute()
            msg = f"Created file {file_path} via API"
    finally:
        os.unlink(tmp_path)
    log.info(msg)
    return msg

def get_calendar_service() -> Optional[Any]:
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        return None
    creds = _load_credentials(creds_path, SCOPES_CALENDAR)
    if not creds:
        return None
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        _calendar_service_cache = service
        return service
    except HttpError as e:
        log.error(f"Failed to build Calendar service: {e}")
        return None
