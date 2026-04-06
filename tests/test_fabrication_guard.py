"""Tests for fabrication_guard module."""

import pytest
from ouroboros.fabrication_guard import (
    verify_response_integrity,
    format_violations_as_message,
    _extract_claims,
    _tool_justifies_claim,
    _is_simple_greeting,
)


def test_extract_claims_basic():
    text = "I see a cat in the image. The file contains 42 rows."
    claims = _extract_claims(text)
    assert len(claims) >= 3
    phrases = [c[1] for c in claims]
    assert "I see" in phrases
    assert "in the image" in phrases
    assert any("contains" in p for p in phrases)


def test_extract_claims_case_insensitive():
    text = "The Picture Shows a dog. I SEE a ball."
    claims = _extract_claims(text)
    phrases = [c[1] for c in claims]
    assert "The Picture Shows" in phrases
    assert "I SEE" in phrases


def test_extract_claims_no_false_positives():
    text = "Hello, how are you? This is a normal statement without visual references."
    claims = _extract_claims(text)
    # Should not detect claims in neutral text
    assert len(claims) == 0


def test_is_simple_greeting():
    assert _is_simple_greeting("Hello")
    assert _is_simple_greeting("Hi there!")
    assert _is_simple_greeting("Thanks")
    assert _is_simple_greeting("Good morning")
    assert not _is_simple_greeting("I see the data")
    assert not _is_simple_greeting("The image shows a cat")


def test_verify_response_integrity_clean():
    # No claims — should pass
    text = "The specification requires 8 GPUs with 141GB each."
    messages = []  # No tool calls; but no claim phrases either
    is_clean, violations = verify_response_integrity(text, messages)
    assert is_clean
    assert not violations


def test_verify_response_integrity_substantiated_claim():
    # Claim with prior tool call that justifies it
    text = "I see 8 GPUs in the image. The file contains 130 rows."
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
        {"role": "tool", "content": "Sheet1: 130 rows"},
    ]
    is_clean, violations = verify_response_integrity(text, messages)
    assert is_clean
    assert not violations


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
    assert "unsubstantiated claim" in violations[0].lower()


def test_verify_response_integrity_mixed_claims():
    # Some claims substantiated, some not
    text = "I see a cat. The file contains 42 rows. The image shows a dog."
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
        {"role": "tool", "content": "rows: 42"},
    ]
    is_clean, violations = verify_response_integrity(text, messages)
    # "The file contains 42 rows" is justified (xlsx_read was called)
    # "I see a cat" and "The image shows a dog" are NOT justified (no vision tool)
    assert not is_clean
    assert len(violations) >= 2  # at least two unsubstantiated visual claims


def test_format_violations_as_message():
    violations = ["Unsubstantiated claim: \"I see\"", "Another violation"]
    msg = format_violations_as_message(violations)
    assert "[FABRICATION GUARD]" in msg
    assert "Unsubstantiated claim: \"I see\"" in msg
    assert "Another violation" in msg
    assert "revise your answer" in msg.lower()


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
    assert _tool_justifies_claim("value is", messages)


def test_tool_justifies_claim_not_present():
    messages = [
        {"role": "user", "content": "hello"},
    ]
    assert not _tool_justifies_claim("I see", messages)
