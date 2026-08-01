"""Web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry
from default_api import web_search as default_web_search


def _web_search_with_real_provider(ctx: ToolContext, query: str) -> str:
    """Performs a web search using a real search provider via default_api.web_search."""
    try:
        # Call the actual web search tool provided by the environment
        result = default_web_search(query=query)
        # The result from default_web_search is already JSON, so just return it
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": repr(e)}, ensure_ascii=False)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("web_search", {
            "name": "web_search",
            "description": "Search the web via a real search provider. Returns JSON with answer + sources.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
            }, "required": ["query"]},
        }, _web_search_with_real_provider),
    ]
