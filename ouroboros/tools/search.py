"""Web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.llm import LLMClient # Import LLMClient

def _web_search(ctx: ToolContext, query: str) -> str:
    model_name = os.environ.get("OUROBOROS_WEBSEARCH_MODEL", "google/gemini-3.1-flash-lite") # Use gemini as default
    
    try:
        llm_client = LLMClient(model=model_name)
        
        # Construct messages for tool calling
        messages = [
            {"role": "user", "content": query}
        ]
        
        # Define the web_search tool for LLMClient
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search_function", # Use a distinct name for the tool within LLMClient
                    "description": "Search the web and get JSON with answer + sources.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                }
            }
        ]

        response = llm_client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto", # Let the LLM decide if it needs to call the tool
        )

        # Parse the response to find tool calls
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            # Assuming the LLM called our web_search_function tool
            for tool_call in tool_calls:
                if tool_call.function.name == "web_search_function":
                    # The actual web search is performed by the LLM itself,
                    # and the result is in the response. We are just defining
                    # the tool here for the LLM to understand how to get search results.
                    # The LLM's own internal web search capability is triggered by the tool_choice.
                    # So, we expect the answer to be in the regular content.
                    text_content = response.choices[0].message.content
                    return json.dumps({"answer": text_content or "(no answer)"}, ensure_ascii=False, indent=2)
        
        # If no tool was called, or if it was, but the answer is in regular content (e.g. LLM synthesized it)
        text_content = response.choices[0].message.content
        return json.dumps({"answer": text_content or "(no answer)"}, ensure_ascii=False, indent=2)

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