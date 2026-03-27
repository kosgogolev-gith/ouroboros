"""Web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry

# Models valid for OpenAI Responses API (direct OpenAI, not OpenRouter)
_OPENAI_NATIVE_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o1", "o3"}

def _resolve_websearch_model() -> str:
    """Return an OpenAI-native model for web search. Falls back to gpt-4o-mini."""
    model = os.environ.get("OUROBOROS_WEBSEARCH_MODEL", "")
    # OpenRouter models contain '/' (e.g. 'google/gemini-2.0-flash-001') — not valid for OpenAI API
    if not model or "/" in model or not any(model.startswith(m) for m in _OPENAI_NATIVE_MODELS):
        return "gpt-4o-mini"
    return model


def _web_search(ctx: ToolContext, query: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "OPENAI_API_KEY not set; web_search unavailable."})
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        model = _resolve_websearch_model()
        resp = client.responses.create(
            model=model,
            tools=[{"type": "web_search_preview"}],  # fixed: was "web_search"
            tool_choice="auto",
            input=query,
        )
        d = resp.model_dump()
        text = ""
        for item in d.get("output", []) or []:
            if item.get("type") == "message":
                for block in item.get("content", []) or []:
                    if block.get("type") in ("output_text", "text"):
                        text += block.get("text", "")
        return json.dumps({"answer": text or "(no answer)"}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": repr(e)}, ensure_ascii=False)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("web_search", {
            "name": "web_search",
            "description": "Search the web via OpenAI Responses API. Returns JSON with answer + sources.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
            }, "required": ["query"]},
        }, _web_search),
    ]
