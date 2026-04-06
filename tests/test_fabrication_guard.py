"""Tests for fabrication_guard module."""

import pytest
from ouroboros.fabrication_guard import (
    _extract_claims,
    _tool_justifies_claim,
    _is_simple_greeting,
    verify_response_integrity,
    format_violations_as_message,
)


def test_extract_claims_basic():
    text = "I see a cat. The file contains 42 rows."
    claims = _extract_claims(text)
    assert len(claims) == 2
    assert any("I see" in phrase for _, phrase, _, _ in claims)
    assert any("contains" in phrase for _, phrase, _, _ in claims)


def test_extract_claims_case_insensitive():
    text = "I SEE the problem. The Image Shows a solution."
    claims = _extract_claims(text)
    assert len(claims) == 2
    categories = [c[3] for c in claims]
    assert "visual" in categories


def test_extract_claims_no_false_positives():
    text = "The price is high. I think we should proceed."
    claims = _extract_claims(text)
    assert len(claims) == 0


def test_is_simple_greeting():
    assert _is_simple_greeting("Hello")
    assert _is_simple_greeting("Hi there!")
    assert _is_simple_greeting("Thanks")
    assert _is_simple_greeting("Good morning")
    assert not _is_simple_greeting("I see the data")
    assert not _is_simple_greeting("The file contains 42 rows")


def test_verify_response_integrity_clean():
    text = "The answer is 42."
    # No claim patterns detected => clean
    is_clean, violations = verify_response_integrity(text, [])
    assert is_clean
    assert len(violations) == 0


def test_verify_response_integrity_substantiated_claim():
    # Visual claim substantiated by vision tool
    text = "I see 8 GPUs in the image."
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
        {"role": "tool", "content": "GPUs: 8"},
    ]
    is_clean, violations = verify_response_integrity(text, messages)
    assert is_clean
    assert len(violations) == 0


def test_verify_response_integrity_unsubstantiated():
    # Claim with no tool call
    text = "I see a cat in the image."
    messages = [
        {"role": "user", "content": "describe photo"},
        {"role": "assistant", "content": "The answer is yes."},
    ]
    is_clean, violations = verify_response_integrity(text, messages)
    assert not is_clean
    assert len(violations) > 0
    assert "unsubstantiated" in violations[0].lower()
    assert "visual" in violations[0].lower()


def test_verify_response_integrity_mixed_claims():
    # Some substantiated, some not
    text = "I see a cat. The file contains 42 rows."
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
        {"role": "tool", "content": "rows: 42"},
    ]
    is_clean, violations = verify_response_integrity(text, messages)
    # "The file contains 42 rows" is justified (xlsx_read was called)
    # "I see a cat" is NOT justified (no vision tool)
    assert not is_clean
    assert len(violations) == 1
    assert "visual" in violations[0].lower()


def test_format_violations_as_message():
    violations = ["Unsubstantiated visual claim: \"I see\" (context: \"...\")"]
    msg = format_violations_as_message(violations)
    assert "[FABRICATION GUARD]" in msg
    assert "Please revise your answer" in msg


def test_tool_justifies_claim_vision():
    # Vision tool called should justify visual claims
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
    ]
    assert _tool_justifies_claim("I see", messages)
    assert _tool_justifies_claim("the image shows", messages)


def test_tool_justifies_claim_data():
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "run_shell"}}]},
    ]
    assert _tool_justifies_claim("running processes", messages)
    assert _tool_justifies_claim("the file contains", messages)


def test_tool_justifies_claim_not_present():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]
    # No tool calls -> does not justify any claim
    assert not _tool_justifies_claim("I see", messages)


# Hardening: ensure we don't accidentally create duplicates or lose functionality
def test_visual_patterns_comprehensive():
    text = "On the screen I see 8 GPUs. The diagram shows 3 NVLink connections. The image clearly appears to be an H200 server. Looking at the photo, the chassis is blue."
    claims = _extract_claims(text)
    categories = {c[3] for c in claims}
    assert "visual" in categories
    assert len(claims) >= 3  # at least 3 visual claims found
