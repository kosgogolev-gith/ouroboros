"""Google API integration via OAuth 2.0.

Provides authenticated clients for Drive, Gmail, Calendar using user credentials.
Falls back to file-based operations if credentials not available or auth fails.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# Scopes for various Google services
SCOPES_DRIVE = ["https://www.googleapis.com/auth/drive.file"]
SCOPES_GMAIL = ["https://www.googleapis.com/auth/gmail.readonly"]
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar.readonly"]

def _load_credentials(credentials_path: str) -> Optional[Credentials]:
    """Load OAuth 2.0 credentials from file, refresh if needed."""
    if not os.path.exists(credentials_path):
        log.warning(f"Credentials file not found: {credentials_path}")
        return None
    try:
        creds = Credentials.from_authorized_user_file(credentials_path, SCOPES_DRIVE)
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

def get_drive_service() -> Optional[Any]:
    """Return an authenticated Drive API service client, or None if not available."""
    global _drive_service_cache
    if _drive_service_cache is not None:
        return _drive_service_cache
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        log.info("GOOGLE_CREDENTIALS_PATH not set — Google API disabled")
        return None
    creds = _load_credentials(creds_path)
    if not creds:
        log.warning("Failed to obtain Google credentials — API disabled")
        return None
    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        _drive_service_cache = service
        return service
    except HttpError as e:
        log.error(f"Failed to build Drive service: {e}")
        return None

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
            import tempfile
            request = service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = googleapiclient.http.MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            content_bytes = fh.getvalue()
            try:
                return content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Try other encodings?
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
    media_body = googleapiclient.http.MediaFileUpload(
        filename,  # We'll write to temp file
        mimetype="text/plain",
        resumable=False,
    )
    # Since we have content as string, write to temp file
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt")
    tmp_path = tmp.name
    tmp.write(content)
    tmp.close()
    try:
        if existing and mode == "overwrite":
            file_id = existing[0]["id"]
            media_body = googleapiclient.http.MediaFileUpload(tmp_path, mimetype="text/plain")
            service.files().update(fileId=file_id, media_body=media_body).execute()
            msg = f"Updated file {file_path} via API"
        else:
            file_metadata = {"name": filename, "parents": [parent_id]}
            media_body = googleapiclient.http.MediaFileUpload(tmp_path, mimetype="text/plain")
            service.files().create(body=file_metadata, media_body=media_body).execute()
            msg = f"Created file {file_path} via API"
    finally:
        os.unlink(tmp_path)
    log.info(msg)
    return msg

# Gmail and Calendar placeholder — can be expanded later
def get_gmail_service() -> Optional[Any]:
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        return None
    creds = _load_credentials(creds_path)
    if not creds:
        return None
    try:
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except HttpError as e:
        log.error(f"Failed to build Gmail service: {e}")
        return None

def get_calendar_service() -> Optional[Any]:
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        return None
    creds = _load_credentials(creds_path)
    if not creds:
        return None
    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except HttpError as e:
        log.error(f"Failed to build Calendar service: {e}")
        return None
