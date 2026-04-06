from typing import Any, Dict, List, Optional, Tuple

from .fabrication_guard import (
    FabricationViolation,
    _handle_text_response as guard_verify,
)
from ouroboros.llm import LLMClient

def _handle_text_response(
    content: Optional[str],
    llm_trace: Dict[str, Any],
    accumulated_usage: Dict[str, Any],
    messages: List[Dict[str, Any]],  # Add the messages argument
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Handle LLM response without tool calls (final response).
    Integrates fabrication guard to verify content integrity.
    """
    if content and content.strip():
        llm_trace["assistant_notes"].append(content.strip()[:320])

    try:
        # Verify content integrity using the fabrication guard
        content = guard_verify(content, messages)
    except FabricationViolation as e:
        content = str(e)
        llm_trace["fabrication_violation"] = str(e)

    return (content or ""), accumulated_usage, llm_trace