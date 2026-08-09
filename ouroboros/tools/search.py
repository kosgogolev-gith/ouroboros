"""Web search tool."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry


def _ddg_search(query: str, max_results: int = 5) -> list:
    """Search via DuckDuckGo — Instant Answer API first, HTML fallback for Russian."""
    import urllib.request, urllib.parse, re
    results = []

    # Try Instant Answer API
    try:
        url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote(query) + "&format=json&no_redirect=1&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Ouroboros/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read())
        if d.get("AbstractText"):
            results.append({"title": d.get("Heading", query), "snippet": d["AbstractText"], "url": d.get("AbstractURL", "")})
        for t in d.get("RelatedTopics", [])[:max_results]:
            if isinstance(t, dict) and t.get("Text"):
                results.append({"title": t.get("Text", "")[:80], "snippet": t.get("Text", ""), "url": t.get("FirstURL", "")})
    except Exception:
        pass

    # HTML fallback (works for Russian)
    if not results:
        try:
            url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            # Extract result snippets
            snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)', html)
            titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
            urls = re.findall(r'class="result__url"[^>]*>([^<]+)', html)
            for i in range(min(max_results, len(snippets))):
                results.append({
                    "title": titles[i].strip() if i < len(titles) else query,
                    "snippet": snippets[i].strip(),
                    "url": urls[i].strip() if i < len(urls) else "",
                })
        except Exception:
            pass

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


def _perplexity_search(query: str) -> str:
    """Search via Perplexity sonar API — returns answer + sources."""
    import urllib.request, os
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        return ""
    payload = json.dumps({
        "model": "sonar",
        "messages": [{"role": "user", "content": query}],
        "max_tokens": 512,
    }).encode()
    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read())
    answer = d["choices"][0]["message"]["content"]
    sources = d.get("citations", [])
    lines = [f"**{query}**\n", answer]
    if sources:
        lines.append("\n**Источники:**")
        for i, s in enumerate(sources[:5], 1):
            lines.append(f"{i}. {s}")
    return "\n".join(lines)


def _web_search_with_real_provider(ctx: ToolContext, query: str) -> str:
    """Search the web. Uses Perplexity sonar (best) with DuckDuckGo fallback."""
    # 1. Perplexity sonar — best quality, supports Russian
    try:
        result = _perplexity_search(query)
        if result:
            return result
    except Exception:
        pass
    # 2. Fallback: DuckDuckGo
    results = []
    try:
        results = _ddg_search(query)
    except Exception:
        pass
    if results:
        lines = [f"**Результаты поиска: {query}**\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r['title']}**")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:200]}")
            if r.get("url"):
                lines.append(f"   🔗 {r['url']}")
        return "\n".join(lines)
    return json.dumps({"error": "No results found", "query": query, "sources": []}, ensure_ascii=False)



def _perplexity_deep_search(ctx: ToolContext, query: str, focus: str = "") -> str:
    """Deep search via Perplexity sonar-pro — detailed answer with sources.
    focus: optional context hint (e.g. 'GPU infrastructure', 'pricing', 'technical specs')
    """
    import urllib.request, os
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        return "❌ PERPLEXITY_API_KEY not set."
    full_query = f"{query}. {focus}" if focus else query
    payload = json.dumps({
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": (
                "You are an expert research assistant. "
                "Provide detailed, structured answers with specific facts, numbers, and dates. "
                "Always cite sources. Respond in the same language as the query."
            )},
            {"role": "user", "content": full_query},
        ],
        "max_tokens": 1024,
    }).encode()
    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read())
    answer = d["choices"][0]["message"]["content"]
    sources = d.get("citations", [])
    lines = [f"🔍 **Deep Search: {query}**\n", answer]
    if sources:
        lines.append("\n**Источники:**")
        for i, s in enumerate(sources[:8], 1):
            lines.append(f"{i}. {s}")
    return "\n".join(lines)


def _document_analyze(ctx: ToolContext, document_text: str, task: str = "",
                       mode: str = "analyze") -> str:
    """Offline document analysis via Perplexity sonar-reasoning-pro (no web search).
    Supports: analyze, summarize, extract, compare, risks, tco.
    """
    import urllib.request, os
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        return "❌ PERPLEXITY_API_KEY not set."

    mode_prompts = {
        "analyze":   "Проанализируй документ детально. Выдели ключевые факты, цифры, условия.",
        "summarize": "Сделай краткое резюме документа (5-10 пунктов).",
        "extract":   "Извлеки все числовые значения, даты, технические характеристики.",
        "compare":   "Сравни характеристики и выдели ключевые различия.",
        "risks":     "Найди риски, несоответствия, подводные камни, неясные формулировки.",
        "tco":       "Рассчитай или оцени совокупную стоимость владения (TCO): CAPEX, OPEX, ROI.",
    }
    system_prompt = mode_prompts.get(mode, mode_prompts["analyze"])
    if task:
        system_prompt += f" Фокус: {task}."

    # Truncate document if too long (128k context limit)
    max_doc_chars = 80000
    if len(document_text) > max_doc_chars:
        document_text = document_text[:max_doc_chars] + "\n\n[...документ обрезан до 80000 символов]"

    payload = json.dumps({
        "model": "sonar-reasoning-pro",
        "messages": [
            {"role": "system", "content": (
                "You are an expert document analyst specializing in technical and commercial documents. "
                "Provide structured, detailed analysis. Respond in Russian unless document is in another language. "
                "No web search needed — analyze only the provided text."
            )},
            {"role": "user", "content": f"{system_prompt}\n\n---\n{document_text}\n---"},
        ],
        "max_tokens": 2048,
    }).encode()

    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read())

    answer = d["choices"][0]["message"]["content"]
    # Strip <think> reasoning tokens if present
    import re
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
    mode_label = {"analyze": "Анализ", "summarize": "Резюме", "extract": "Извлечение данных",
                  "compare": "Сравнение", "risks": "Риски", "tco": "TCO анализ"}.get(mode, "Анализ")
    return f"📄 **{mode_label} документа**\n\n{answer}"

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("web_search", {
            "name": "web_search",
            "description": "Search the web via a real search provider. Returns JSON with answer + sources. If real search is unavailable, it will return an error message indicating this limitation.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
            }, "required": ["query"]},
        }, _web_search_with_real_provider),
        ToolEntry("perplexity_deep_search", {
            "name": "perplexity_deep_search",
            "description": (
                "Deep web search via Perplexity sonar-pro. "
                "Use for complex research: GPU specs, vendor comparison, pricing, technical analysis, "
                "news analysis, competitive intelligence. Returns detailed structured answer + sources. "
                "Slower than web_search but significantly more thorough."
            ),
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Research question or topic"},
                "focus": {"type": "string", "description": "Optional context (e.g. 'GPU infrastructure', 'pricing 2026')", "default": ""},
            }, "required": ["query"]},
        }, _perplexity_deep_search),
        ToolEntry("document_analyze", {
            "name": "document_analyze",
            "description": (
                "Offline document analysis via Perplexity sonar-reasoning-pro (no web search). "
                "Use for: analyzing КП/specs/contracts, extracting numbers, finding risks, TCO calculation. "
                "Paste document text directly. Supports modes: analyze, summarize, extract, compare, risks, tco."
            ),
            "parameters": {"type": "object", "properties": {
                "document_text": {"type": "string", "description": "Full text of the document to analyze"},
                "task": {"type": "string", "description": "Specific task or focus (e.g. 'найди несоответствия в ценах')", "default": ""},
                "mode": {
                    "type": "string",
                    "description": "Analysis mode",
                    "enum": ["analyze", "summarize", "extract", "compare", "risks", "tco"],
                    "default": "analyze"
                },
            }, "required": ["document_text"]},
        }, _document_analyze),
    ]

# Alias for backward compatibility
web_search_tool = _web_search_with_real_provider
