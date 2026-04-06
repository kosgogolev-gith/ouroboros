def _verify_content_integrity(
    final_content: str,
    messages: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Pre-output verification guard: detect unverified claims about image/spec analysis.

    Scans the final response for phrases that suggest the agent has seen/analyzed
    visual or document content that was not actually retrieved via tools.

    Returns:
        None if content passes verification
        Error message string if integrity violation detected
    """
    if not final_content or not final_content.strip():
        return None

    # Patterns indicating claims about visual/document analysis
    # These suggest the agent is describing something it supposedly saw
    suspicious_patterns = [
        r"I see",
        r"I can see",
        r"in the image",
        r"in the photo",
        r"in the picture",
        r"the image shows",
        r"the picture shows",
        r"the photo shows",
        r"based on the image",
        r"from the image",
        r"looking at the image",
        r"analysis of the image",
        r"analysis of the document",
        r"the document shows",
        r"the specification",
        r"the spec shows",
        r"the sheet shows",
        r"the table shows",
        r"according to the image",
        r"according to the document",
        r"according to the spec",
        r"the file contains",
        r"the file shows",
    ]

    import re
    content_lower = final_content.lower()
    for pattern in suspicious_patterns:
        if re.search(pattern, content_lower):
            # Found a suspicious claim. Check if recent tool calls justify it.
            if not _has_recent_visual_tool_success(messages):
                return (
                    "🚨 INTEGRITY VIOLATION: Response contains unverified claims about "
                    "image/document analysis without corresponding tool execution. "
                    "This violates Principle 4 (Authenticity) and Principle 3 (LLM-First). "
                    "The guard blocked the response to prevent fabrication."
                )
            # If we find evidence of tool use, allow
            break

    return None


def _has_recent_visual_tool_success(
    messages: List[Dict[str, Any]],
    lookback_rounds: int = 10,
) -> bool:
    """
    Check if there is a successful tool call that could justify visual/spec claims.

    Looks at recent assistant messages with tool_calls and the following tool results.
    Success means tool call was made and result does NOT start with "⚠️".
    """
    # Tools that produce visual or document data
    relevant_tools = {
        "browse_page", "analyze_screenshot", "xlsx_read", "pdf_read",
        "spec_compare", "drive_read", "repo_read", "codebase_digest",
        "web_search", "chat_history"
    }

    # Scan messages in reverse, looking at assistant tool_calls and the subsequent tool responses
    i = len(messages) - 1
    rounds_checked = 0
    while i >= 0 and rounds_checked < lookback_rounds:
        msg = messages[i]
        role = msg.get("role")
        if role == "assistant" and "tool_calls" in msg:
            # Found an assistant message that called tools. Check if any of those tools are relevant and succeeded.
            tool_calls = msg["tool_calls"]
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                if fn_name in relevant_tools:
                    # Now look ahead for the tool result
                    # The result should be in the message immediately after
                    if i + 1 < len(messages):
                        next_msg = messages[i + 1]
                        if next_msg.get("role") == "tool" and next_msg.get("tool_call_id") == tc.get("id"):
                            result_content = next_msg.get("content", "")
                            if not result_content.startswith("⚠️"):
                                return True
            rounds_checked += 1
        i -= 1

    return False


def _handle_text_response(
    content: Optional[str],
    llm_trace: Dict[str, Any],
    accumulated_usage: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Handle LLM response without tool calls (final response).

    Returns: (final_text, accumulated_usage, llm_trace)
    """
    # Fabrication guard: check content integrity before allowing response
    if content:
        integrity_error = _verify_content_integrity(content, messages)
        if integrity_error:
            # Block the response and return an error message and request correction
            # The supervisor will handle this as a task failure and re-prompt the agent
            return integrity_error, accumulated_usage, llm_trace

    if content and content.strip():
        llm_trace["assistant_notes"].append(content.strip()[:320])
    return (content or ""), accumulated_usage, llm_trace