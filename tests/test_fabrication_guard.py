"""Tests for fabrication_guard module."""

import pytest
import json
from ouroboros.fabrication_guard import (
    _extract_claims,
    _is_simple_greeting,
    _tool_justifies_category,
    _verify_content_integrity,
    _handle_text_response,
    FabricationViolation,
    COMPILED_PATTERNS,
)


class TestExtractClaims:
    def test_extract_basic(self):
        text = "I see a cat. The image shows a dog. The file contains 42."
        claims = _extract_claims(text)
        pattern_keys = [p for p, _ in claims]
        assert "see" in pattern_keys
        assert "image shows" in pattern_keys
        assert "file contains" in pattern_keys

    def test_case_insensitive(self):
        text = "I SEE an apple. THE IMAGE SHOWS a tree."
        claims = _extract_claims(text)
        pattern_keys = [p.lower() for p, _ in claims]
        assert any("see" in k for k in pattern_keys)
        assert any("image shows" in k for k in pattern_keys)

    def test_no_false_positives(self):
        text = "This is a book about seeing into the future. The image of success is important."
        claims = _extract_claims(text)
        pattern_keys = [p.lower() for p, _ in claims]
        # Should not match "seeing" or "image of" (not "image shows")
        assert not any("seeing" in k for k in pattern_keys)
        assert not any("image of" in k for k in pattern_keys)

    def test_visual_patterns_comprehensive(self):
        text = (
            "I see the cat. "
            "In the image, a dog. "
            "The picture shows a car. "
            "The photo shows a house. "
            "Based on the image, we conclude. "
            "The photo depicts a person. "
            "The screenshot shows an error. "
            "The snapshot shows progress."
        )
        claims = _extract_claims(text)
        pattern_keys = [p for p, _ in claims]
        assert "see" in pattern_keys
        assert "in the image" in pattern_keys
        assert "picture shows" in pattern_keys
        assert "photo shows" in pattern_keys
        assert "based on the image" in pattern_keys
        assert "photo depicts" in pattern_keys
        assert "screenshot shows" in pattern_keys
        assert "snapshot shows" in pattern_keys


class TestIsSimpleGreeting:
    def test_greeting(self):
        assert _is_simple_greeting("Hello!")
        assert _is_simple_greeting("Hi there.")
        assert _is_simple_greeting("Hey, what's up?")

    def test_not_greeting(self):
        assert not _is_simple_greeting("I see the image shows a cat.")
        assert not _is_simple_greeting("The file contains data.")
        assert not _is_simple_greeting("Hello, what does the image show?")


class TestToolJustifiesCategory:
    def test_vision_tool_matching(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": json.dumps({"description": "cat"})},
        ]
        assert _tool_justifies_category("vision", msgs)

    def test_vision_tool_failed_no_response(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
        ]
        assert not _tool_justifies_category("vision", msgs)

    def test_vision_tool_failed_with_error(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": json.dumps({"error": "failed"})},
        ]
        assert not _tool_justifies_category("vision", msgs)

    def test_wrong_category(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
            {"role": "tool", "name": "xlsx_read", "content": json.dumps({"row_count": 42})},
        ]
        assert not _tool_justifies_category("vision", msgs)

    def test_data_tool_matching(self):
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
            {"role": "tool", "name": "xlsx_read", "content": json.dumps({"row_count": 42})},
        ]
        assert _tool_justifies_category("data", msgs)

    def test_no_tool_calls(self):
        msgs = [{"role": "user", "content": "Hello"}]
        assert not _tool_justifies_category("vision", msgs)


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
            {"role": "tool", "name": "analyze_screenshot", "content": json.dumps({"description": "cat"})},
        ]
        result = _verify_content_integrity(content, msgs)
        assert result is None

    def test_mixed_claims_vision_and_data(self):
        content = "I see a cat. The file contains 42 rows."
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": json.dumps({"description": "cat"})},
            {"role": "assistant", "tool_calls": [{"function": {"name": "xlsx_read"}}]},
            {"role": "tool", "name": "xlsx_read", "content": json.dumps({"row_count": 42})},
        ]
        result = _verify_content_integrity(content, msgs)
        assert result is None

    def test_greeting_not_flagged(self):
        content = "Hello"
        msgs = []
        assert _verify_content_integrity(content, msgs) is None


class TestHandleTextResponse:
    def test_accepts_clean_content(self):
        content = "All systems go."
        msgs = []
        result = _handle_text_response(content, msgs)
        assert result == content

    def test_raises_on_visual_fabrication(self):
        content = "I see the image shows the device."
        msgs = []
        with pytest.raises(FabricationViolation):
            _handle_text_response(content, msgs)

    def test_accepts_when_verified(self):
        content = "I see the image shows the device."
        msgs = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "analyze_screenshot"}}]},
            {"role": "tool", "name": "analyze_screenshot", "content": json.dumps({"description": "device"})},
        ]
        result = _handle_text_response(content, msgs)
        assert result == content
