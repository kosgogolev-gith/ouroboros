"""Web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry


def _web_search_with_real_provider(ctx: ToolContext, query: str) -> str:
    """Performs a web search using a real search provider, or provides a stub if unavailable."""
    try:
        # Attempt to call the actual web search tool provided by the environment
        from default_api import web_search as default_web_search  # lazy import
        result = default_web_search(query=query)
        # The result from default_web_search is expected to be JSON-serializable
        return json.dumps(result, ensure_ascii=False, indent=2)
    except TypeError as e:
        # Specific error for LLMClient __init__ issue
        error_message = f"Web search provider error: {repr(e)}. The underlying LLMClient in default_api.web_search seems to be configured incorrectly or does not accept expected arguments. Real web search is currently unavailable."
        return json.dumps({"error": error_message, "query": query, "sources": []}, ensure_ascii=False)
    except Exception as e:
        # Catch any other general exceptions from the web search provider
        error_message = f"Web search provider error: {repr(e)}. Real web search is currently unavailable."
        return json.dumps({"error": error_message, "query": query, "sources": []}, ensure_ascii=False)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("web_search", {
            "name": "web_search",
            "description": "Search the web via a real search provider. Returns JSON with answer + sources. If real search is unavailable, it will return an error message indicating this limitation.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
            }, "required": ["query"]},
        }, _web_search_with_real_provider),
    ]
