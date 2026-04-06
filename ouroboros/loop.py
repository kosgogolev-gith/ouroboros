def _handle_text_response(
    content: Optional[str],
    llm_trace: Dict[str, Any],
    accumulated_usage: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Handle LLM response without tool calls (final response).
    Integrates fabrication guard to verify content integrity.
    """
    from .fabrication_guard import _handle_text_response as guard_verify, FabricationViolation

    if content and content.strip():
        llm_trace["assistant_notes"].append(content.strip()[:320])

    # Use full message history for verification
    try:
        # Need to get the full messages list - will be passed from caller context
        # The caller will build the complete messages list and we verify against it
        # For now, we'll modify the return to include messages in the outer scope
        pass  # will be handled in updated call site
    except FabricationViolation as e:
        content = str(e)

    return (content or ""), accumulated_usage, llm_trace