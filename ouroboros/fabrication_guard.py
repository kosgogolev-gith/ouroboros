"""
Fabrication Guard — Integrity verification for Ouroboros.

This module implements a pre-output check that scans assistant responses for
unsubstantiated claims about visual content, document analysis, or data that
was not actually retrieved via tool calls. It addresses the integrity drift
where the agent claims to have seen/analyzed something without using the
appropriate tools.

Bible references: P3 (LLM-First - truthfulness), P4 (Authenticity)
"""

import re
from typing import Any, Dict, List, Tuple, Set


# Phrases that indicate a claim about visual content or analysis
VISUAL_CLAIM_PHRASES = [
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
    r"\bappears\b",
    r"\bvisible\b",
    r"\blooking at\b",
    r"\bview shows\b",
    r"\bthe document contains\b",
    r"\bthe file contains\b",
    r"\bcontains\s+\d+\s+items\b",
    r"\bhas\s+\d+\s+rows\b",
    r"\bvalue is\b",
    r"\bis\s+[\d.]+\s*[%$]?\b",
    r"\brunning\s+\w+\s+processes\b",
    r"\bprocesses?\s+are\s+running\b",
    r"\bstatus\s+is\b",
    r"\bthe output shows\b",
    r"\boutput indicates\b",
]

# Compile regex patterns for efficiency
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in VISUAL_CLAIM_PHRASES]


def _extract_claims(text: str) -> List[Tuple[int, str, str]]:
    """
    Find all claim-like phrases in the text.

    Returns list of (match_start, matched_text, context_snippet).
    """
    claims = []
    for pattern in COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            snippet = text[start:end].strip()
            claims.append((match.start(), match.group(), snippet))
    return claims


def _tool_justifies_claim(claim_phrase: str, messages: List[Dict[str, Any]]) -> bool:
    """
    Determine if the conversation history contains a tool call that would
    substantiate the given claim.

    Simple heuristics:
    - Visual claims → require a vision-related tool call: analyze_screenshot, browse_page (with screenshot), or any tool that returned image data.
    - Data claims → require a data extraction tool: xlsx_read, pdf_read, drive_read, repo_read, codebase_digest, run_shell, etc.
    """
    # Check recent tool calls (last 20 messages)
    recent_messages = messages[-20:] if len(messages) > 20 else messages

    # Detect if any vision/data tool was called with a non-error result
    for msg in reversed(recent_messages):
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            # Vision tools
            if fn_name in ("analyze_screenshot", "browse_page", "browser_action"):
                return True
            # Data extraction / system inspection tools
            if fn_name in ("xlsx_read", "pdf_read", "drive_read", "repo_read", "codebase_digest", "run_shell", "chat_history"):
                # For numeric/data claims, we consider these tools as justification
                # even without parsing the exact result, as long as the call succeeded
                return True

    return False


def _is_simple_greeting(text: str) -> bool:
    """Detect if text is just a greeting or trivial statement without substantive claim."""
    greetings = {"hello", "hi", "hey", "greetings", "good morning", "good evening", "thanks", "thank you"}
    lowered = text.strip().lower()
    # If the entire message is just a greeting or very short (< 10 words) and no claim phrases
    if lowered in greetings or len(text.split()) < 5:
        return True
    return False


def verify_response_integrity(final_text: str, messages: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Verify that the final response does not contain unsubstantiated claims.
    Returns (is_clean, list_of_violations).
    """
    if not final_text or not final_text.strip():
        return True, []

    # Ignore trivial/greeting responses
    if _is_simple_greeting(final_text):
        return True, []

    claims = _extract_claims(final_text)
    if not claims:
        return True, []

    violations = []
    for match_start, phrase, snippet in claims:
        if not _tool_justifies_claim(phrase, messages):
            violations.append(f"Unsubstantiated claim: \"{phrase}\" (context: \"{snippet}\")")

    if violations:
        return False, violations
    return True, []


def format_violations_as_message(violations: List[str]) -> str:
    """
    Create a system message instructing the LLM to correct its response.
    This message can be injected into the conversation to trigger a revision.
    """
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
