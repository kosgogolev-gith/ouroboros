# -*- coding: utf-8 -*-
"""
Supervisor — Telegram client + formatting.

TelegramClient, message splitting, markdown→HTML conversion, send_with_budget.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from supervisor.state import load_state, save_state, append_jsonl

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level config (set via init())
# ---------------------------------------------------------------------------
DRIVE_ROOT = None  # pathlib.Path
TOTAL_BUDGET_LIMIT: float = 0.0
BUDGET_REPORT_EVERY_MESSAGES: int = 100
REPLY_USE_MARKDOWN: bool = True
TELEGRAM_PARSE_MODE: str = "MarkdownV2"
MAX_MESSAGE_LENGTH: int = 4096
OWNER_IDS: set[int] = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _escape_markdown(text: str) -> str:
    """Escape characters for Telegram MarkdownV2."""
    escape_chars = r'[_*\[\]()~`>#+-=|{}.!\\-]'
    return re.sub(escape_chars, r'\\\g<0>', text)


def markdown_to_html(text: str) -> str:
    """Very simple Markdown → HTML conversion for Telegram HTML parse mode."""
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Italic
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    # Inline code
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    return text


# ---------------------------------------------------------------------------
# TelegramClient
# ---------------------------------------------------------------------------
class TelegramClient:
    """
    Wrapper around Telegram Bot API.

    Features:
    - get_updates (long polling)
    - send_message with budget tracking and split logic
    - image download support
    """

    def __init__(self, token: str, base: Optional[str] = None):
        self.token = token
        self.base = base or f"https://api.telegram.org/bot{token}"

    def get_updates(self, offset: int, timeout: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch updates from Telegram.

        Returns list of update objects.
        """
        last_err = "unknown"
        for attempt in range(3):
            try:
                r = requests.get(
                    f"{self.base}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": timeout,
                        "allowed_updates": ["message", "edited_message", "channel_post"],
                    },
                    timeout=timeout + 5,
                )
                r.raise_for_status()
                data = r.json()
                if data.get("ok") is not True:
                    raise RuntimeError(f"Telegram getUpdates failed: {data}")
                return data.get("result") or []
            except Exception as e:
                last_err = repr(e)
                if attempt < 2:
                    continue
                raise RuntimeError(f"Telegram getUpdates failed after 3 attempts: {last_err}")

    def download_file(self, file_path: str) -> bytes:
        """
        Download a file from Telegram servers given its file_path.

        Returns raw bytes.
        """
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.content

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_buttons: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Send a message to the user with budget tracking and split logic.
        """
        # Estimate tokens: 1 token ≈ 4 characters (rough)
        est_tokens = max(1, len(text) // 4)
        estimated_cost = (est_tokens / 1_000_000) * 0.00001  # tiny cost

        # Check budget
        state = load_state()
        if state.get("spent_usd", 0.0) + estimated_cost > TOTAL_BUDGET_LIMIT:
            log.error("Budget limit exceeded, cannot send message")
            return

        actual_send = False
        if reply_buttons:
            # TODO: implement button rendering into inline keyboard JSON
            reply_markup = {"inline_keyboard": reply_buttons}
            r = requests.post(
                f"{self.base}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode or TELEGRAM_PARSE_MODE,
                    "reply_markup": reply_markup,
                },
                timeout=30,
            )
            r.raise_for_status()
            actual_send = True
        else:
            if len(text) <= MAX_MESSAGE_LENGTH:
                r = requests.post(
                    f"{self.base}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode or TELEGRAM_PARSE_MODE,
                    },
                    timeout=30,
                )
                r.raise_for_status()
                actual_send = True
            else:
                # Split into parts
                parts: List[str] = []
                while len(text) > MAX_MESSAGE_LENGTH:
                    # Find a safe split point (double newline or space)
                    split_at = text.rfind("\n\n", 0, MAX_MESSAGE_LENGTH)
                    if split_at == -1:
                        split_at = text.rfind(" ", 0, MAX_MESSAGE_LENGTH)
                    if split_at == -1:
                        split_at = MAX_MESSAGE_LENGTH
                    parts.append(text[:split_at])
                    text = text[split_at:].lstrip()
                parts.append(text)

                for part in parts:
                    r = requests.post(
                        f"{self.base}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": part,
                            "parse_mode": parse_mode or TELEGRAM_PARSE_MODE,
                        },
                        timeout=30,
                    )
                    r.raise_for_status()
                    actual_send = True

        if actual_send:
            # Track approximate budget impact
            state = load_state()
            state["spent_usd"] = state.get("spent_usd", 0.0) + estimated_cost
            save_state(state)

    def get_me(self) -> Dict[str, Any]:
        r = requests.get(f"{self.base}/getMe", timeout=10)
        r.raise_for_status()
        return r.json()["result"]
