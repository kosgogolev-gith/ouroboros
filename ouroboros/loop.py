class FabricationViolation(Exception):
    """Raised when response contains unverified visual/spec claims that violate integrity."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _verify_content_integrity(
    final_content: str,
    messages: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Pre-output verification guard: detect unverified claims about image/spec analysis.

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


def _handle_text_response(
    content: Optional[str],
    messages: List[Dict[str, Any]],
) -> str:
    """
    Final response validation. Raises FabricationViolation if content fails integrity check.
    """
    if content:
        integrity_error = _verify_content_integrity(content, messages)
        if integrity_error:
            raise FabricationViolation(integrity_error)

    return content or """


def run_llm_loop(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: str,
    llm_client,
    usage: Dict[str, Any],
    llm_trace: Dict[str, Any],
    task_id: Optional[str] = None,
    max_llm_rounds: int = 25,
    owner_message: Optional[str] = None,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    # ... existing loop code ...
    # when handling text-only final response:
    #   text = _handle_text_response(content, messages)
    #   return text, usage, llm_trace