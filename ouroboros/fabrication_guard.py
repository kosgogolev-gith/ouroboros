"""Fabrication Guard — Integrity verification for Ouroboros."""

import re
from typing import Any, Dict, List, Tuple, Set


# Phrases indicating visual content claims
VISUAL_CLAIM_PATTERNS = [
    r"\bI see\b",
    r"\bin the image\b",
    r"\bthe image shows\b",
    r"\bthe picture shows\b",
    r"\bthe photo shows\b",
    r"\bthe screenshot shows\b",
    r"\bthe video shows\b",
    r"\bthe diagram shows\b",
    r"\bon the screen\b",
    r"\bappears to be\b",
    r"\bappears\b(?!\s+to\s+have\s+been\s+verified)",  # caution: match "appears" when it indicates visual impression
    r"\bvisible\b",
    r"\blooking at\b",
    r"\bview shows\b",
]

# Phrases indicating numeric/data claims
DATA_CLAIM_PATTERNS = [
    r"\bthe document contains\b",
    r"\bthe file contains\b",
    r"\bcontains\s+\d+\s+items\b",
    r"\bhas\s+\d+\s+rows\b",
    r"\bvalue is\b",
    r"\bis\s+[\d.]+\s*[%$]?\b",
    r"\brunning\s+\d+\s+processes\b",
    r"\bprocesses?\s+are\s+running\b",
    r"\bstatus\s+is\b",
    r"\bthe output shows\b",
    r"\boutput indicates\b",
    r"\b\d+\s+items?\s+found\b",
    r"\bfound\s+\d+\b",
]

# Compile all patterns and keep mapping to category
COMPILED_PATTERNS: List[Tuple[re.Pattern, str]] = []
for pat in VISUAL_CLAIM_PATTERNS:
    COMPILED_PATTERNS.append((re.compile(pat, re.IGNORECASE), "visual"))
for pat in DATA_CLAIM_PATTERNS:
    COMPILED_PATTERNS.append((re.compile(pat, re.IGNORECASE), "data"))


def _extract_claims(text: str) -> List[Tuple[int, str, str, str]]:
    """
    Find all claim-like phrases in the text.

    Returns list of (match_start, matched_text, snippet, category).
    Category: "visual", "data", or "other" (should not occur).
    """
    claims = []
    for pattern, category in COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            snippet = text[start:end].strip()
            claims.append((match.start(), match.group(), snippet, category))
    # Sort by position to preserve order
    claims.sort(key=lambda x: x[0])
    return claims


def _tool_justifies_claim(claim_category: str, messages: List[Dict[str, Any]]) -> bool:
    """
    Determine if the conversation history contains a tool call that would
    substantiate a claim of the given category.

    Visual claim → vision tools: analyze_screenshot, browse_page, browser_action
    Data claim → data tools: xlsx_read, pdf_read, drive_read, repo_read, codebase_digest, run_shell, chat_history, get_task_result, etc.
    """
    # Check recent messages (last 30)
    recent_messages = messages[-30:] if len(messages) > 30 else messages

    for msg in reversed(recent_messages):
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            continue
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            if claim_category == "visual":
                if fn_name in ("analyze_screenshot", "browse_page", "browser_action"):
                    return True
            elif claim_category == "data":
                if fn_name in ("xlsx_read", "pdf_read", "drive_read", "repo_read", "codebase_digest", "run_shell", "chat_history", "get_task_result", "wait_for_task", "list_available_tools"):
                    return True
            # Other categories not yet defined
    return False


def _is_simple_greeting(text: str) -> bool:
    """Detect if text is just a greeting or trivial statement without substantive claims."""
    greetings = {"hello", "hi", "hey", "greetings", "good morning", "good evening", "good afternoon", "thanks", "thank you", "ok", "okay", "understood", "noted"}
    lowered = text.strip().lower()
    if lowered in greetings:
        return True
    # Very short (<6 words) and no claim phrases (quick check)
    if len(text.split()) < 6:
        # If it contains claim patterns, it's not just a greeting
        for pattern, _ in COMPILED_PATTERNS:
            if pattern.search(text):
                return False
        return True
    return False


def verify_response_integrity(final_text: str, messages: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Verify that the final response does not contain unsubstantiated claims.
    Returns (is_clean, list_of_violations).
    """
    if not final_text or not final_text.strip():
        return True, []

    # Ignore trivial greetings only if there are no claim phrases at all
    if _is_simple_greeting(final_text):
        # But still check if there are any claim patterns; if yes, not a simple greeting
        for pattern, _ in COMPILED_PATTERNS:
            if pattern.search(final_text):
                break
        else:
            return True, []

    claims = _extract_claims(final_text)
    if not claims:
        return True, []

    violations = []
    for match_start, phrase, snippet, category in claims:
        if not _tool_justifies_claim(category, messages):
            violations.append(f"Unsubstantiated {category} claim: \"{phrase}\" (context: \"{snippet}\")")

    if violations:
        return False, violations
    return True, []


def format_violations_as_message(violations: List[str]) -> str:
    """Create a system message instructing the LLM to correct its response."""
    lines = [
        "[FABRICATION GUARD] Your response contains the following unsubstantiated claims:",
    ]
    for v in violations:
        lines.append(f"  • {v}")
    lines.extend([
        "",
        "Please revise your answer to only include information you have actually obtained through tool calls.",
        "If you need to verify something, call the appropriate tool first.",
        "Do not describe what you think you see without using a vision tool.",
        "Do not state numeric facts without referencing extracted data.",
        "Provide your corrected response now, without further tool calls if possible."
    ])
    return "\n".join(lines)
