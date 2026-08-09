"""STT (Speech-to-Text) tools for Ouroboros — Whisper via OpenRouter."""
import base64
import json
import logging
import os
import urllib.request
from typing import List

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Transcribe audio bytes via Whisper on OpenRouter."""
    key = os.environ.get("OUROBOROS_STT_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    base_url = os.environ.get("OUROBOROS_STT_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("OUROBOROS_STT_MODEL", "openai/whisper-large-v3")

    if not key:
        return "[STT error: no API key]"

    boundary = "OuroborosBoundary7MA4"
    mime = "audio/ogg" if filename.endswith(".ogg") else "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"{model}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + audio_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read())
    return d.get("text", "").strip()


def _stt_from_base64(ctx, audio_base64: str, filename: str = "audio.ogg") -> str:
    """Transcribe audio from base64-encoded bytes."""
    try:
        audio_bytes = base64.b64decode(audio_base64)
        text = _transcribe_audio(audio_bytes, filename=filename)
        return text if text else "[STT: пусто — тишина или неразборчиво]"
    except Exception as e:
        return f"[STT error: {e}]"


def _stt_from_telegram_file(ctx, file_id: str) -> str:
    """Download voice message from Telegram by file_id and transcribe it."""
    try:
        import sys
        # Try to get TG bot instance from supervisor
        tg_module = sys.modules.get("supervisor.telegram") or sys.modules.get("ouroboros.supervisor.telegram")
        if tg_module and hasattr(tg_module, "TG") and tg_module.TG:
            b64, mime = tg_module.TG.download_file_base64(file_id)
            if b64:
                audio_bytes = base64.b64decode(b64)
                text = _transcribe_audio(audio_bytes, filename="voice.ogg")
                return text if text else "[STT: пусто]"
            return "[STT error: не удалось скачать файл]"
        return "[STT error: Telegram не инициализирован]"
    except Exception as e:
        return f"[STT error: {e}]"


def get_tools() -> List:
    if ToolEntry is None:
        return []
    return [
        ToolEntry(
            "stt_transcribe",
            {
                "name": "stt_transcribe",
                "description": (
                    "Transcribe audio to text using Whisper. "
                    "Provide audio as base64-encoded string. "
                    "Supports ogg (Telegram voice), mp3, wav. "
                    "Returns transcribed text in the original language."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "audio_base64": {"type": "string", "description": "Base64-encoded audio bytes"},
                        "filename": {"type": "string", "description": "Filename hint for format (voice.ogg, audio.mp3)", "default": "audio.ogg"},
                    },
                    "required": ["audio_base64"],
                },
            },
            _stt_from_base64,
        ),
        ToolEntry(
            "stt_from_telegram",
            {
                "name": "stt_from_telegram",
                "description": (
                    "Transcribe a Telegram voice message by file_id. "
                    "Use when a voice message arrives in chat — pass its file_id directly. "
                    "Returns transcribed text."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string", "description": "Telegram file_id of the voice message"},
                    },
                    "required": ["file_id"],
                },
            },
            _stt_from_telegram_file,
        ),
    ]
