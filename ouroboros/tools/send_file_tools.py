"""send_file tool for Ouroboros — send files to owner via Telegram."""
import base64
import logging
import os
import pathlib
import sys
from typing import List, Optional

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _get_tg():
    """Get TelegramClient from colab_launcher module."""
    # TG is initialized in colab_launcher scope
    for mod_name in ("__main__", "colab_launcher"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "TG"):
            return mod.TG
    return None


def _get_owner_chat_id() -> Optional[int]:
    """Get owner chat_id from state."""
    try:
        import json, pathlib
        state_path = pathlib.Path.home() / "ouroboros_data" / "state" / "state.json"
        d = json.loads(state_path.read_text())
        return int(d.get("owner_chat_id", 0)) or None
    except Exception:
        return None


def _send_file(ctx, file_path: str = "", content_text: str = "",
               filename: str = "", caption: str = "",
               file_base64: str = "") -> str:
    """Send a file to the owner via Telegram.

    Provide one of:
    - file_path: local file path (reads from disk)
    - content_text: text content (saved as .txt and sent)
    - file_base64: base64-encoded file bytes

    filename: displayed filename in Telegram (default: basename of file_path)
    caption: optional message caption
    """
    try:
        tg = _get_tg()
        if not tg:
            return "❌ Telegram не инициализирован. Этот инструмент работает только в runtime."

        chat_id = _get_owner_chat_id()
        if not chat_id:
            return "❌ owner_chat_id не найден в state.json"

        # Determine bytes and filename
        if file_path:
            p = pathlib.Path(file_path).expanduser()
            if not p.exists():
                return f"❌ Файл не найден: {file_path}"
            file_bytes = p.read_bytes()
            if not filename:
                filename = p.name
            # Guess mime type
            suffix = p.suffix.lower()
            mime_map = {
                ".pdf": "application/pdf",
                ".txt": "text/plain",
                ".md": "text/markdown",
                ".json": "application/json",
                ".csv": "text/csv",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".zip": "application/zip",
                ".py": "text/x-python",
                ".log": "text/plain",
            }
            mime_type = mime_map.get(suffix, "application/octet-stream")

        elif content_text:
            file_bytes = content_text.encode("utf-8")
            if not filename:
                filename = "output.txt"
            mime_type = "text/plain"

        elif file_base64:
            file_bytes = base64.b64decode(file_base64)
            if not filename:
                filename = "file"
            mime_type = "application/octet-stream"

        else:
            return "❌ Укажи file_path, content_text или file_base64"

        # Size check (Telegram limit: 50MB)
        size_mb = len(file_bytes) / 1024 / 1024
        if size_mb > 50:
            return f"❌ Файл слишком большой: {size_mb:.1f} MB (лимит Telegram 50 MB)"

        ok, err = tg.send_document(
            chat_id=chat_id,
            file_bytes=file_bytes,
            filename=filename,
            caption=caption or f"📎 {filename}",
            mime_type=mime_type,
        )

        if ok:
            return f"✅ Файл отправлен: **{filename}** ({size_mb:.2f} MB)"
        return f"❌ Ошибка отправки: {err}"

    except Exception as e:
        return f"❌ Ошибка: {e}"



def _drive_to_telegram(ctx, drive_path: str, caption: str = "") -> str:
    """Read a file from Google Drive and send it to owner via Telegram in one step.

    This is the correct way to send Drive files — combines drive_read + send_file.
    drive_path: relative to Ouroboros Drive root (e.g. 'memory/report.md', 'my_skills.md')
    """
    try:
        # Step 1: read from Drive
        from ouroboros.integrations.google.drive import read_file as _drive_read_file
        text = _drive_read_file(drive_path)
        if not text or text.startswith("❌") or "not found" in text.lower():
            return f"❌ Файл не найден на Drive: {drive_path}"

        # Step 2: send via Telegram
        filename = drive_path.split("/")[-1]
        result = _send_file(ctx, content_text=text, filename=filename,
                           caption=caption or f"📎 {filename} (с Google Drive)")
        return result
    except Exception as e:
        return f"❌ drive_to_telegram ошибка: {e}"


def get_tools() -> List:
    if ToolEntry is None:
        return []
    return [
        ToolEntry(
            "send_file",
            {
                "name": "send_file",
                "description": (
                    "Send a file to the owner via Telegram. "
                    "Send a file to the owner via Telegram. "
                    "IMPORTANT: file_path must be a LOCAL filesystem path (e.g. /tmp/report.md). "
                    "Google Drive files are NOT local paths — use drive_read first, then content_text. "
                    "To send a Drive file: 1) drive_read path=X -> get text, 2) send_file content_text=<text> filename=X. "
                    "Supports: pdf, txt, md, json, csv, xlsx, docx, png, jpg, zip, py, log. Max 50MB."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Local file path", "default": ""},
                        "content_text": {"type": "string", "description": "Text content to send as a .txt file", "default": ""},
                        "file_base64": {"type": "string", "description": "Base64-encoded file bytes", "default": ""},
                        "filename": {"type": "string", "description": "Filename shown in Telegram", "default": ""},
                        "caption": {"type": "string", "description": "Caption message", "default": ""},
                    },
                    "required": [],
                },
            },
            _send_file,
        ),
        ToolEntry(
            "drive_to_telegram",
            {
                "name": "drive_to_telegram",
                "description": (
                    "Read a file from Google Drive and send it to owner via Telegram in ONE step. "
                    "Use this instead of combining drive_read + send_file manually. "
                    "drive_path: relative path on Drive (e.g. 'memory/report.md', 'my_skills.md'). "
                    "This is the CORRECT way to send Drive files to owner."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drive_path": {"type": "string", "description": "Relative path on Google Drive"},
                        "caption": {"type": "string", "default": ""},
                    },
                    "required": ["drive_path"],
                },
            },
            _drive_to_telegram,
        ),
    ]