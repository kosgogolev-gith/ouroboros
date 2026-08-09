"""summary_webpage tool — fetch a URL and summarize via LLM."""
import logging
import urllib.request
import urllib.error
from typing import List

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _fetch_text(url: str, max_chars: int = 20000) -> str:
    """Fetch URL and extract readable text."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "ru,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")

    # Strip HTML tags
    import re
    text = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _summary_webpage(ctx, url: str, question: str = "",
                     mode: str = "summarize", lang: str = "ru") -> str:
    """Fetch a webpage and summarize or answer a question about it.

    mode: summarize | extract | qa | full
    lang: ru | en
    """
    try:
        # Fetch page
        text = _fetch_text(url)
        if not text or len(text) < 100:
            return f"❌ Не удалось получить текст с {url} (пустая страница или недоступна)"

        # Build prompt
        lang_inst = "Отвечай на русском языке." if lang == "ru" else "Answer in English."
        prompts = {
            "summarize": f"Сделай краткое резюме этой страницы (5-10 пунктов). {lang_inst}",
            "extract": f"Извлеки ключевые факты, цифры, даты и имена. {lang_inst}",
            "qa": f"Ответь на вопрос: {question}\n{lang_inst}" if question else f"Опиши главную тему страницы. {lang_inst}",
            "full": f"Подробно опиши содержимое страницы. {lang_inst}",
        }
        prompt = prompts.get(mode, prompts["summarize"])
        full_prompt = f"{prompt}\n\n---\nURL: {url}\n\n{text[:15000]}\n---"

        # Use Perplexity sonar (offline, no web search) or LLM
        import os
        pplx_key = os.environ.get("PERPLEXITY_API_KEY", "")
        if pplx_key:
            import json
            payload = json.dumps({
                "model": "sonar",
                "messages": [{"role": "user", "content": full_prompt}],
                "max_tokens": 1024,
            }).encode()
            req = urllib.request.Request(
                "https://api.perplexity.ai/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {pplx_key}",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            answer = d["choices"][0]["message"]["content"]
        elif ctx and ctx.llm:
            msg, _ = ctx.llm.chat(
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=1024,
            )
            answer = msg.get("content", "")
        else:
            # Just return extracted text
            return f"📄 **{url}**\n\n{text[:3000]}"

        return f"🌐 **{url}**\n\n{answer}"

    except urllib.error.URLError as e:
        return f"❌ Ошибка доступа к {url}: {e.reason}"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def get_tools() -> List:
    if ToolEntry is None:
        return []
    return [
        ToolEntry(
            "summary_webpage",
            {
                "name": "summary_webpage",
                "description": (
                    "Fetch a URL and summarize its content using AI. "
                    "Use for: reading articles, news, documentation, КП по ссылке. "
                    "Modes: summarize (default), extract (facts/numbers), qa (answer question), full (detailed). "
                    "Works without Playwright — pure HTTP request."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch and summarize"},
                        "question": {"type": "string", "description": "Question to answer about the page (for mode=qa)", "default": ""},
                        "mode": {
                            "type": "string",
                            "enum": ["summarize", "extract", "qa", "full"],
                            "default": "summarize",
                        },
                        "lang": {"type": "string", "enum": ["ru", "en"], "default": "ru"},
                    },
                    "required": ["url"],
                },
            },
            _summary_webpage,
        ),
    ]
