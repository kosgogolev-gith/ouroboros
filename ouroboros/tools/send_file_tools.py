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
                    "Use to share reports, logs, generated PDFs, CSV exports, code files. "
                    "Provide file_path (local path), content_text (text to send as file), "
                    "or file_base64 (base64 bytes). "
                    "Supports: pdf, txt, md, json, csv, xlsx, docx, png, jpg, zip, py, log."
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
    ]
