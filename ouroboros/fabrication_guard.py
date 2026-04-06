"""Fabrication Guard — Integrity verification for Ouroboros."""

import re
import json
from typing import List, Tuple, Optional

# ============================================================================
# Public exception class
# ============================================================================

class FabricationViolation(Exception):
    """Raised when response content integrity check fails."""
    def __init__(self, message: str, claims: List[Tuple[str, str]]):
        super().__init__(message)
        self.claims = claims


# ============================================================================
# Claim patterns (refined)
# ============================================================================

VISUAL_PATTERNS = [
    # Exact phrase patterns requiring vision backing
    (r'\b(I\s+can\s+)?see\b', 'see'),
    (r'\bthe\s+image\s+shows?\b', 'image shows'),
    (r'\bthe\s+picture\s+shows?\b', 'picture shows'),
    (r'\bthe\s+photo\s+shows?\b', 'photo shows'),
    (r'\bthe\s+photo\s+depicts\b', 'photo depicts'),
    (r'\bbased\s+on\s+the\s+image\b', 'based on the image'),
    (r'\bin\s+the\s+image\b', 'in the image'),
    (r'\bthe\s+screenshot\s+shows?\b', 'screenshot shows'),
    (r'\bthe\s+snapshot\s+shows?\b', 'snapshot shows'),
]

DATA_PATTERNS = [
    (r'\bthe\s+file\s+contains\b', 'file contains'),
    (r'\bthe\s+data\s+shows\b', 'data shows'),
    (r'\bthe\s+table\s+shows\b', 'table shows'),
    (r'\bthe\s+spreadsheet\s+contains\b', 'spreadsheet contains'),
    (r'\brows?\s+number\b', 'rows number'),
    (r'\bcount\s+of\b', 'count of'),
]

ALL_PATTERNS = VISUAL_PATTERNS + DATA_PATTERNS
COMPILED_PATTERNS = [(re.compile(pat, re.I), key) for (pat, key) in ALL_PATTERNS]

# ============================================================================
# Tool mapping by category
# ============================================================================

def _tool_category(tool_name: str) -> Optional[str]:
    nm = tool_name.lower()
    if nm in {"analyze_screenshot", "browse_page", "browser_action", "analyze_image", "analyze_photo"}:
        return "vision"
    if nm in {
        "xlsx_read", "pdf_read", "drive_read", "repo_read",
        "codebase_digest", "codebase_tree", "codebase_search",
        "list_github_issues", "get_github_issue", "chat_history",
        "knowledge_read", "spec_compare", "xlsx_reader", "tool_discovery", "web_search"
    }:
        return "data"
    return None


# ============================================================================
# Claim extraction
# ============================================================================

def _extract_claims(text: str) -> List[Tuple[str, str]]:
    """Return list of (pattern_key, snippet) for each claim in text."""
    claims = []
    for regex, key in COMPILED_PATTERNS:
        for m in regex.finditer(text):
            start = max(m.start() - 30, 0)
            end = min(m.end() + 30, len(text))
            snippet = text[start:end].strip()
            claims.append((key, snippet))
    return claims


# ============================================================================
# Greeting detection
# ============================================================================

def _is_simple_greeting(text: str) -> bool:
    text_low = text.strip().lower()
    if len(text_low.split()) <= 3:
        greetings = {"hi", "hello", "hey", "greetings", "good morning", "good evening"}
        if any(g in text_low for g in greetings):
            return True
    return False


# ============================================================================
# Tool presence helpers
# ============================================================================

def _find_last_tool_call_of_category(messages: List[dict], category: str) -> Optional[dict]:
    """
    Scan messages backwards to find the last assistant tool call whose name maps to the given category.
    Return the assistant message dict containing tool_calls, or None.
    """
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            tool_name = m["tool_calls"][0]["function"]["name"]
            if _tool_category(tool_name) == category:
                return m
    return None


def _tool_call_successful(tool_msg: dict) -> bool:
    try:
        data = json.loads(tool_msg.get("content", ""))
        if data.get("error") or data.get("exception"):
            return False
        return True
    except Exception:
        return True


def _tool_justifies_category(category: str, messages: List[dict]) -> bool:
    """
    Return True if there exists a successful tool call of the given category
    that appears before the current turn (i.e., in the recent past).
    """
    # Find the most recent assistant message with a tool call of this category
    assistant_msg = _find_last_tool_call_of_category(messages, category)
    if not assistant_msg:
        return False
    tool_name = assistant_msg["tool_calls"][0]["function"]["name"]

    # Find the corresponding tool response that should appear immediately after
    # messages list is ordered from oldest to newest; find index of assistant_msg
    try:
        idx = messages.index(assistant_msg)
    except ValueError:
        return False
    next_idx = idx + 1
    if next_idx < len(messages):
        next_msg = messages[next_idx]
        if next_msg.get("role") == "tool" and next_msg.get("name") == tool_name:
            return _tool_call_successful(next_msg)
    return False


# ============================================================================
# Core verification
# ============================================================================

def _verify_content_integrity(content: str, messages: List[dict]) -> Optional[str]:
    if _is_simple_greeting(content):
        return None

    claims = _extract_claims(content)
    if not claims:
        return None

    violating_claims = []
    for pattern_key, snippet in claims:
        # Determine category from pattern key: if key in vision patterns list
        if any(key == pattern_key for _, key in VISUAL_PATTERNS):
            category = "vision"
        else:
            category = "data"

        if not _tool_justifies_category(category, messages):
            violating_claims.append(f"- Unsubstantiated: '{snippet}' (pattern: {pattern_key})")

    if violating_claims:
        return ("INTEGRITY VIOLATION: The following claims are not backed by tool data:\n" +
                "\n".join(violating_claims) +
                "\nPlease revise to remove or substantiate them. Do not claim to see or analyze what you haven't actually processed.")
    return None


def _handle_text_response(content: str, messages: List[dict]) -> str:
    violation = _verify_content_integrity(content, messages)
    if violation:
        raise FabricationViolation(violation, [])
    return content


def _format_violation_as_message(violation: FabricationViolation) -> dict:
    return {
        "role": "system",
        "content": str(violation)
    }
