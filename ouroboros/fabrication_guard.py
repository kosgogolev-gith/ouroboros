"""Fabrication Guard — Integrity verification for Ouroboros."""

import re
from typing import List, Tuple, Optional, Set
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
# Claim patterns
# ============================================================================

VISUAL_PATTERNS = [
    # Exact phrase patterns
    (r'\bI\s+see\b', 'see'),
    (r'\bthe\s+image\s+shows\b', 'image shows'),
    (r'\bthe\s+picture\s+shows\b', 'picture shows'),
    (r'\bthe\s+photo\s+shows\b', 'photo shows'),
    (r'\bbased\s+on\s+the\s+image\b', 'based on the image'),
    (r'\bin\s+the\s+image\b', 'in the image'),
    (r'\bthe\s+photo\s+depicts\b', 'photo depicts'),
    (r'\bthe\s+screenshot\s+shows\b', 'screenshot shows'),
    (r'\bthe\s+snapshot\s+shows\b', 'snapshot shows'),
    # Documented specs (stated facts)
    (r'\bthe\s+specification\s+(says|states|requires)\b', 'specification'),
    (r'\bthe\s+requirements\s+(say|state)\b', 'requirements'),
    # Data extraction claims
    (r'\bthe\s+file\s+contains\b', 'file contains'),
    (r'\bthe\s+data\s+shows\b', 'data shows'),
    (r'\bthe\s+table\s+shows\b', 'table shows'),
    (r'\bthe\s+spreadsheet\s+contains\b', 'spreadsheet contains'),
    (r'\brows?\s+number\b', 'rows number'),
    (r'\bcount\s+of\b', 'count of'),
]

COMPILED_PATTERNS = [(re.compile(pat, re.I), key) for (pat, key) in VISUAL_PATTERNS]

# ============================================================================
# Tool mapping by category
# ============================================================================

def _tool_category(tool_name: str) -> Optional[str]:
    nm = tool_name.lower()
    if nm in {"analyze_screenshot", "browse_page", "browser_action", "analyze_image"}:
        return "vision"
    if nm in {
        "xlsx_read", "pdf_read", "drive_read", "repo_read",
        "codebase_digest", "codebase_tree", "codebase_search",
        "list_github_issues", "get_github_issue", "chat_history",
        "knowledge_read"
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

def _has_recent_vision_tool(messages: List[dict]) -> bool:
    """Check if the last tool call (if any) was a vision tool and succeeded."""
    # Find last assistant message with tool_calls
    last_tool_call = None
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            last_tool_call = m["tool_calls"][0]["function"]["name"]
            break
        if m.get("role") == "tool":
            # We reached a tool response; the preceding assistant was already matched
            break
    if not last_tool_call:
        return False
    return _tool_category(last_tool_call) == "vision"

def _tool_call_successful(tool_msg: dict) -> bool:
    """Check if a tool message indicates success (no 'error' or 'exception' field with truthy value)."""
    content = tool_msg.get("content", "")
    # JSON string -> dict for simplicity
    try:
        import json
        data = json.loads(content)
        if data.get("error") or data.get("exception"):
            return False
        return True
    except Exception:
        return True  # if not JSON, assume successful

def _tool_justifies_category(category: str, messages: List[dict]) -> bool:
    """Return True if a recent tool call of the given category succeeded."""
    # Find last assistant tool call of this category
    last_tool_name = None
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            last_tool_name = m["tool_calls"][0]["function"]["name"]
            if _tool_category(last_tool_name) == category:
                break
        if m.get("role") == "tool":
            # We passed the tool call and found its response
            break
    if not last_tool_name:
        return False
    # Find corresponding tool response message
    for m in reversed(messages):
        if m.get("role") == "tool" and m.get("name") == last_tool_name:
            return _tool_call_successful(m)
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
        category = "vision" if pattern_key in {
            "see", "image shows", "picture shows", "photo shows",
            "based on the image", "in the image", "photo depicts",
            "screenshot shows", "snapshot shows"
        } else "data"
        if not _tool_justifies_category(category, messages):
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
        # Attach context for the LLM to understand what is expected
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
