
from typing import Literal
from ouroboros.tools.registry import register_tool
from ouroboros.tools.llm import get_llm
from ouroboros.tools.browser import browse_page

@register_tool
def summary_webpage(url: str) -> str:
    """Делает саммаризацию страницы по ссылке: краткое содержание и вывод.

    Args:
        url: URL страницы для саммаризации.
    """
    try:
        page_content = browse_page(url=url, output="text")
        if not page_content or not page_content.get("text"):
            return "Не удалось получить содержимое страницы."

        text_to_summarize = page_content["text"]
        
        # Использование языковой модели для саммаризации
        llm = get_llm()
        prompt = f"""Сделай краткое содержание и основные выводы по следующему тексту:

{text_to_summarize[:8000]} # Ограничиваем размер текста для LLM, чтобы избежать переполнения контекста

Краткое содержание и выводы:
"""
        summary_response = llm.complete(prompt)
        
        return summary_response.text

    except Exception as e:
        return f"Произошла ошибка при саммаризации страницы: {e}"

def get_tools():
    return [summary_webpage]
