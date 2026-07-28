"""Google Drive API client with high-level file operations.

Provides simple functions for file management:
- list_files(path): list files/folders in a folder
- read_file(path) -> str: read text file content
- write_file(path, content, mode): create/update files
- delete_file(path): delete files/folders

Handles path resolution, MIME types, and retry logic for quota errors.
"""

import os
import time
from pathlib import Path
from typing import Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from .auth import authenticate


# Build service singleton with lazy initialization
_service = None


def _get_service():
    """Get or create the Drive service instance."""
    global _service
    if _service is None:
        creds = authenticate()
        _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _service


# Retry configuration for quota/transient errors
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_FACTOR = 2.0


def _execute_with_retry(request, operation: str = "API request"):
    """Execute a Drive API request with exponential backoff on quota errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return request.execute()
        except HttpError as e:
            if e.resp.status in (403, 429, 500, 502, 503, 504):
                if attempt == MAX_RETRIES - 1:
                    raise
                wait_time = INITIAL_BACKOFF * (BACKOFF_FACTOR**attempt)
                print(f"⚠️ {operation} failed with {e.resp.status}, retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                raise
    raise RuntimeError("Max retries exceeded")


def _path_to_folder_id(path: str, create_missing: bool = False) -> Tuple[str, str]:
    """
    Resolve a Drive path to a folder ID.

    Args:
        path: Absolute or relative path (e.g., "/folder/subfolder" or "folder/subfolder")
        create_missing: Create folders if they don't exist (for write operations)

    Returns:
        (folder_id, folder_name) where folder_id is the Drive folder ID, folder_name is the last component
    """
    service = _get_service()

    # Normalize path: strip leading/trailing slashes, split
    path = path.strip("/")
    if not path:
        # Root directory
        return ("root", "")

    parts = path.split("/")
    folder_name = parts[-1]
    parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

    # Resolve parent folder ID
    if parent_path:
        parent_id, _ = _path_to_folder_id(parent_path, create_missing=False)
    else:
        parent_id = "root"

    # Check if the folder with this name exists in the parent
    query = (
        f"name = '{folder_name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = _execute_with_retry(
        service.files().list(q=query, fields="files(id, name)"),
        operation=f"list folder '{folder_name}'"
    )
    files = results.get("files", [])

    if files:
        folder_id = files[0]["id"]
        return (folder_id, folder_name)

    if create_missing:
        # Create the folder
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = _execute_with_retry(
            service.files().create(body=file_metadata, fields="id, name"),
            operation=f"create folder '{folder_name}'"
        )
        print(f"📁 Created folder: {path} (ID: {folder.get('id')})")
        return (folder.get("id"), folder_name)

    raise FileNotFoundError(f"Folder not found: {path}")


def list_files(path: str = ".") -> list[dict]:
    """
    List files and folders in a given path.

    Args:
        path: Path to list (default current folder '.')

    Returns:
        List of dicts with keys: id, name, mimeType, size, modifiedTime
    """
    service = _get_service()

    try:
        folder_id, _ = _path_to_folder_id(path, create_missing=False)
    except FileNotFoundError:
        return []

    query = (
        f"'{folder_id}' in parents and "
        f"trashed = false"
    )
    results = _execute_with_retry(
        service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)"
        ),
        operation="list files"
    )
    return results.get("files", [])


def _get_file_id(path: str) -> str:
    """Get the Drive file ID for a given path."""
    path = path.strip("/")
    if not path:
        raise ValueError("Empty path")

    parts = path.split("/")
    parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
    file_name = parts[-1]

    if parent_path:
        parent_id, _ = _path_to_folder_id(parent_path, create_missing=False)
    else:
        parent_id = "root"

    # Search for file (not folder) with exact name in parent
    query = (
        f"name = '{file_name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType != 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    service = _get_service()
    results = _execute_with_retry(
        service.files().list(q=query, fields="files(id, name)"),
        operation=f"find file '{file_name}'"
    )
    files = results.get("files", [])
    if not files:
        raise FileNotFoundError(f"File not found: {path}")
    if len(files) > 1:
        # Multiple files with same name - pick the latest modified
        files.sort(key=lambda f: f.get("modifiedTime", ""), reverse=True)
    return files[0]["id"]


def read_file(path: str) -> str:
    """
    Read text file content from Google Drive.

    Args:
        path: Path to the file

    Returns:
        File content as string (UTF-8 decoded)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file MIME type is not a text format
    """
    service = _get_service()
    file_id = _get_file_id(path)

    # Get file metadata to check MIME type
    file = _execute_with_retry(
        service.files().get(fileId=file_id, fields="mimeType, name"),
        operation="get file metadata"
    )
    mime_type = file.get("mimeType", "")

    # Only allow text-based MIME types
    allowed_mime_prefixes = [
        "text/",
        "application/json",
        "application/xml",
        "application/yaml",
        "application/javascript",
        "application/typescript",
        "application/csv",
        "application/rtf",
        "application/x-python-code",
        "application/x-shellscript",
        "application/x-makefile",
    ]
    if not any(mime_type.startswith(prefix) or mime_type == prefix for prefix in allowed_mime_prefixes):
        raise ValueError(
            f"Cannot read file '{path}': MIME type '{mime_type}' is not a supported text format. "
            "Only plain text files (code, configs, data) are supported."
        )

    # Download content
    request = service.files().get_media(fileId=file_id)
    from io import BytesIO
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    content_bytes = fh.getvalue()
    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"File '{path}' is not valid UTF-8: {e}")


def write_file(path: str, content: str, mode: str = "overwrite") -> dict:
    """
    Write content to a file on Google Drive.

    Args:
        path: Destination path
        content: Text content to write
        mode: "overwrite" (default) or "append"

    Returns:
        Dict with file metadata: {"id": ..., "name": ..., "modifiedTime": ...}
    """
    service = _get_service()

    path = path.strip("/")
    if not path:
        raise ValueError("Empty path")

    parts = path.split("/")
    file_name = parts[-1]
    parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

    # Resolve parent folder ID (create if needed)
    if parent_path:
        parent_id, _ = _path_to_folder_id(parent_path, create_missing=True)
    else:
        parent_id = "root"

    # Determine MIME type based on file extension
    ext = Path(file_name).suffix.lower()
    mime_map = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".py": "text/x-python",
        ".js": "application/javascript",
        ".ts": "application/typescript",
        ".html": "text/html",
        ".css": "text/css",
        ".xml": "application/xml",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".sh": "application/x-shellscript",
        ".bash": "application/x-shellscript",
        ".zsh": "application/x-shellscript",
        ".toml": "application/toml",
        ".ini": "text/plain",
        ".cfg": "text/plain",
        ".conf": "text/plain",
        ".log": "text/plain",
    }
    mime_type = mime_map.get(ext, "text/plain")

    # Check if file already exists
    existing_file_id = None
    try:
        existing_file_id = _get_file_id(path)
    except FileNotFoundError:
        pass  # Will create new file

    media = MediaFileUpload(
        None,  # We'll provide content directly
        mimetype=mime_type,
        resumable=True,
    )

    if existing_file_id and mode == "overwrite":
        # Update existing file
        request = service.files().update(
            fileId=existing_file_id,
            media_body=media,
            body={"name": file_name},
        )
        # MediaFileUpload needs a file-like object; we'll patch it
        media.stream = content.encode("utf-8")
        media.mimetype = mime_type
        file = _execute_with_retry(request, operation="update file")
        action = "updated"
    elif existing_file_id and mode == "append":
        # Read existing content, append, then update
        existing_content = read_file(path)
        new_content = existing_content + content
        media.stream = new_content.encode("utf-8")
        request = service.files().update(
            fileId=existing_file_id,
            media_body=media,
            body={"name": file_name},
        )
        file = _execute_with_retry(request, operation="append to file")
        action = "appended"
    else:
        # Create new file
        file_metadata = {
            "name": file_name,
            "parents": [parent_id],
            "mimeType": mime_type,
        }
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, modifiedTime",
        )
        media.stream = content.encode("utf-8")
        file = _execute_with_retry(request, operation="create file")
        action = "created"

    print(f"📄 File {action}: {path} (ID: {file.get('id')})")
    return {
        "id": file.get("id"),
        "name": file.get("name"),
        "modifiedTime": file.get("modifiedTime"),
    }


def delete_file(path: str) -> bool:
    """
    Delete a file or folder from Google Drive.

    Args:
        path: Path to delete

    Returns:
        True if deleted successfully

    Raises:
        FileNotFoundError: If the file/folder doesn't exist
    """
    service = _get_service()
    file_id = _get_file_id(path)
    # For folders, _get_file_id also works if we search by name and parent,
    # but we need to allow mimeType = folder. We'll adjust by trying to get metadata first.
    try:
        file = _execute_with_retry(
            service.files().get(fileId=file_id, fields="mimeType"),
            operation="get file metadata for delete"
        )
        mime_type = file.get("mimeType")
        is_folder = mime_type == "application/vnd.google-apps.folder"
    except HttpError as e:
        if e.resp.status == 404:
            raise FileNotFoundError(f"File not found: {path}")
        raise

    # For folders, also need to recursively delete contents? Drive API deletion of folder
    # automatically deletes all children. So we can just delete the folder.
    _execute_with_retry(
        service.files().delete(fileId=file_id),
        operation="delete file/folder"
    )
    item_type = "folder" if is_folder else "file"
    print(f"🗑️ {item_type.title()} deleted: {path} (ID: {file_id})")
    return True
