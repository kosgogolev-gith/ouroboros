"""Fabrication Guard — Integrity verification for Ouroboros."""

import re
import json
from typing import List, Tuple, Optional
from dataclasses import dataclass

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
    (r'\bI\s+see\b', 'see'),
    (r'\bthe\s+image\s+shows?\b', 'image shows'),
    (r'\bthe\s+picture\s+shows?\b', 'picture shows'),
    (r'\bthe\s+photo\s+shows?\b', 'photo shows'),
    (r'\bthe\s+photo\s+depicts\b', 'photo depicts'),
    (r'\bbased\s+on\s+the\s+image\b', 'based on the image'),
    (r'\bin\s+the\s+image\b', 'in the image'),
    (r'\bthe\s+screenshot\s+shows?\b', 'screenshot shows'),
    (r'\bthe\s+snapshot\s+shows?\b', 'snapshot shows'),
    # Spec/requirements are considered non-fabrication if they come from knowledge base? We'll ignore for now.
    # Documented specs (stated facts) — these may be from knowledge, not vision; treat as NOT requiring verification now.
    # (r'\bthe\s+specification\s+(says|states|requires)\b', 'specification'),
    # (r'\bthe\s+requirements\s+(say|state)\b', 'requirements'),
]

COMPILED_PATTERNS = [(re.compile(pat, re.I), key) for (pat, key) in VISUAL_PATTERNS]

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
        "knowledge_read", "spec_compare", "xlsx_reader", "tool_discovery"
    }:
        return "data"
    # web_search returns search results but not raw images directly; treat as data
    if nm == "web_search":
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
    """Heuristic to avoid fabricating in pure greetings."""
    text_low = text.strip().lower()
    if len(text_low.split()) <= 3:
        greetings = {"hi", "hello", "hey", "greetings", "good morning", "good evening"}
        if any(g in text_low for g in greetings):
            return True
    return False


# ============================================================================
# Tool presence helpers
# ============================================================================

def _find_last_assistant_tool_call(messages: List[dict]) -> Optional[dict]:
    """
    Return the last assistant message that has tool_calls, or None.
    Also note if that tool_call has a corresponding tool response after it.
    """
    for i in range(len(messages)-1, -1, -1):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            return {"assistant_idx": i, "tool_call": m["tool_calls"][0]["function"]}
    return None


def _tool_call_successful(tool_msg: dict) -> bool:
    """Check if a tool message indicates success (no 'error' or 'exception' field with truthy value)."""
    try:
        data = json.loads(tool_msg.get("content", ""))
        if data.get("error") or data.get("exception"):
            return False
        return True
    except Exception:
        return True  # if not JSON, assume successful


def _tool_justifies_category(category: str, messages: List[dict]) -> bool:
    """
    Return True if there exists a successful tool call of the given category
    that appears before the current user/assistant turn (i.e., in the recent past).
    """
    # Find the last assistant tool call of the desired category
    pair = _find_last_assistant_tool_call(messages)
    if not pair:
        return False
    tool_name = pair["tool_call"]["name"]
    if _tool_category(tool_name) != category:
        return False

    # Look for a tool response immediately following that assistant message
    assistant_idx = pair["assistant_idx"]
    next_idx = assistant_idx + 1
    if next_idx < len(messages):
        next_msg = messages[next_idx]
        if next_msg.get("role") == "tool" and next_msg.get("name") == tool_name:
            return _tool_call_successful(next_msg)
    return False


# ============================================================================
# Core verification
# ============================================================================

def _verify_content_integrity(content: str, messages: List[dict]) -> Optional[str]:
    """
    Verify that any claim about visual or document content in `content` is
    substantiated by a recent successful tool call of the appropriate category.
    Returns violation message string if check fails, None if all clear.
    """
    if _is_simple_greeting(content):
        return None

    claims = _extract_claims(content)
    if not claims:
        return None

    violating_claims = []
    for pattern_key, snippet in claims:
        category = "vision"
        if category == "vision" and not _tool_justifies_category("vision", messages):
            violating_claims.append(f"- Unsubstantiated: '{snippet}' (pattern: {pattern_key})")

    if violating_claims:
        return ("INTEGRITY VIOLATION: The following claims are not backed by tool data:\n" +
                "\n".join(violating_claims) +
                "\nPlease revise to remove or substantiate them. Do not claim to see or analyze what you haven't actually processed.")
    return None


# ============================================================================
# Wrappers used by core loop
# ============================================================================

def _handle_text_response(content: str, messages: List[dict]) -> str:
    """
    Wrap response content with integrity verification. If violations found,
    raise FabricationViolation to force retry.
    """
    violation = _verify_content_integrity(content, messages)
    if violation:
        raise FabricationViolation(violation, [])
    return content


def _format_violation_as_message(violation: FabricationViolation) -> dict:
    """
    Create a system message that explains fabrication rules for debugging.
    """
    return {
        "role": "system",
        "content": str(violation)
    }
