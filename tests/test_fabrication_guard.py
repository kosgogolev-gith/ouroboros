"""Tests for fabrication_guard module."""

import pytest
from ouroboros.fabrication_guard import (
    _extract_claims,
    _is_simple_greeting,
    _has_recent_vision_tool,
    _tool_call_successful,
    _verify_content_integrity,
    _handle_text_response,
    FabricationViolation,
    COMPILED_PATTERNS,
)


class TestExtractClaims:
    def test_extract_basic(self):
        text = "I see a cat. The image shows a dog. The file contains 42."
        claims = _extract_claims(text)
        # All visual claims are captured:
        assert ("see", "I see") in claims or any("see" in p for p, _ in claims)
        assert ("image shows", "the image shows") in claims
        assert ("file contains", "the file contains") in claims

    def test_case_insensitive(self):
        text = "I SEE an apple. THE IMAGE SHOWS a tree."
        claims = _extract_claims(text)
        # Should contain the patterns regardless of case
        patterns = [p for p, _ in claims]
        assert any("see" in p.lower() for p in patterns)
        assert any("image shows" in p.lower() for p in patterns)

    def test_no_false_positives(self):
        text = "This is a book about seeing into the future. The image of success is important."
        claims = _extract_claims(text)
        # Should only match the intended patterns
        for pattern, snippet in claims:
            # Should be start of sentence or preceded by non-word
            assert pattern in ["see", "image shows", "file contains"]
            assert pattern in snippet.lower()

    def test_visual_patterns_comprehensive(self):
        text = (
            "I see the cat. "
            "In the image, a dog. "
            "The picture shows a car. "
            "The photo shows a house. "
            "Based on the image, we conclude. "
            "The specification says X. "
            "The file contains data. "
            "The table shows values."
        )
        claims = _extract_claims(text)
        patterns = [p for p, _ in claims]
        assert any("see" in p for p in patterns)
        assert any("in the image" in p for p in patterns)
        assert any("picture shows" in p for p in patterns)
        assert any("photo shows" in p for p in patterns)
        assert any("based on the image" in p for p in patterns)
        assert any("specification" in p for p in patterns)
        assert any("file contains" in p for p in patterns)
        assert any("table shows" in p for p in patterns)


class TestIsSimpleGreeting:
    def test_greeting(self):
        assert _is_simple_greeting("Hello!")
        assert _is_simple_greeting("Hi there.")
        assert _is_simple_greeting("Hey, what's up?")

    def test_not_greeting(self):
        assert not _is_simple_greeting("I see the image shows a cat.")
        assert not _is_simple_greeting("The file contains data.")
        assert not _is_simple_greeting("Hello, what does the image show?")


class TestHasRecentVisionTool:
    def test_successful_vision_tool(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": '{"description": "..."}'}
        ]
        assert _has_recent_vision_tool(msgs)

    def test_vision_tool_failed(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": '{"error": "failed"}'}
        ]
        assert not _has_recent_vision_tool(msgs)

    def test_no_vision_tool(self):
        msgs = [{"role": "user", "content": "Hello"}]
        assert not _has_recent_vision_tool(msgs)


class TestToolCallSuccessful:
    def test_successful(self):
        msg = {"role": "tool", "content": '{"ok": true}'}
        assert _tool_call_successful(msg)

    def test_failure_by_error_field(self):
        msg = {"role": "tool", "content": '{"error": "something failed"}'}
        assert not _tool_call_successful(msg)

    def test_failure_by_exception(self):
        msg = {"role": "tool", "content": '{"exception": "boom"}'}
        assert not _tool_call_successful(msg)


class TestVerifyResponseIntegrity:
    def test_clean(self):
        content = "The project plan looks solid. I recommend proceeding."
        msgs = []
        result = _verify_content_integrity(content, msgs)
        assert result is None

    def test_unsubstantiated_visual(self):
        content = "I can see the image clearly shows a cat."
        msgs = []  # no tool calls
        result = _verify_content_integrity(content, msgs)
        assert result is not None
        assert "INTEGRITY VIOLATION" in result

    def test_substantiated_visual(self):
        content = "I can see the image clearly shows a cat."
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": '{"description": "cat"}'},
        ]
        result = _verify_content_integrity(content, msgs)
        assert result is None

    def test_mixed_claims(self):
        content = "I see a cat. The file contains 42 rows."
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
            {"role": "tool", "name": "xlsx_read", "content": '{"row_count": 42}'},
        ]
        result = _verify_content_integrity(content, msgs)
        assert result is None

    def test_uncaught_truthful_data_claim(self):
        content = "The data shows an upward trend."
        msgs = []
        result = _verify_content_integrity(content, msgs)
        # This should not be flagged as fabrication
        assert result is None


class TestHandleTextResponse:
    def test_accepts_clean_content(self):
        content = "All systems go."
        msgs = []
        result = _handle_text_response(content, msgs)
        assert result == content

    def test_raises_on_visual_fabrication(self):
        content = "I see the image shows the device."
        msgs = []
        with pytest.raises(FabricationViolation) as exc:
            _handle_text_response(content, msgs)
        assert "INTEGRITY VIOLATION" in str(exc.value)

    def test_accepts_when_verified(self):
        content = "I see the image shows the device."
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": '{"description": "device"}'},
        ]
        result = _handle_text_response(content, msgs)
        assert result == content
