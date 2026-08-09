"""Web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry


def _ddg_search(query: str, max_results: int = 5) -> list:
    """Search via DuckDuckGo Instant Answer API — no key needed."""
    import urllib.request, urllib.parse
    url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote(query) + "&format=json&no_redirect=1&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Ouroboros/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read())
    results = []
    # Abstract (instant answer)
    if d.get("AbstractText"):
        results.append({"title": d.get("Heading", query), "snippet": d["AbstractText"], "url": d.get("AbstractURL", "")})
    # Related topics
    for t in d.get("RelatedTopics", [])[:max_results]:
        if isinstance(t, dict) and t.get("Text"):
            results.append({"title": t.get("Text", "")[:80], "snippet": t.get("Text", ""), "url": t.get("FirstURL", "")})
    return results


def _brave_search(query: str, max_results: int = 5) -> list:
    """Search via Brave Search API if key is available."""
    import urllib.request, urllib.parse, os
    key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not key:
        return []
    url = "https://api.search.brave.com/res/v1/web/search?q=" + urllib.parse.quote(query) + f"&count={max_results}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read())
    return [{"title": r.get("title",""), "snippet": r.get("description",""), "url": r.get("url","")}
            for r in d.get("web", {}).get("results", [])[:max_results]]


def _web_search_with_real_provider(ctx: ToolContext, query: str) -> str:
    """Performs a web search. Uses Brave Search API if key set, otherwise DuckDuckGo."""
    results = []
    error = None
    # 1. Try Brave (best quality)
    try:
        results = _brave_search(query)
    except Exception:
        pass
    # 2. Fallback to DuckDuckGo
    if not results:
        try:
            results = _ddg_search(query)
        except Exception as e:
            error = str(e)
    if results:
        lines = [f"**Результаты поиска: {query}**\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r['title']}**")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:200]}")
            if r.get("url"):
                lines.append(f"   🔗 {r['url']}")
        return "\n".join(lines)
    return json.dumps({"error": error or "No results found", "query": query, "sources": []}, ensure_ascii=False)


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

# Alias for backward compatibility
web_search_tool = _web_search_with_real_provider
