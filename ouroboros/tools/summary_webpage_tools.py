
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any

# Assuming default_api is available in the context for browse_page and chat completions
# This will be injected by the runtime environment.
# from ouroboros.loop import LLMLoop

def get_tools() -> list[Dict[str, Any]]:
    """Returns a list of tool definitions for the summary_webpage skill."""
    return [
        {
            "name": "summary_webpage",
            "description": "Саммаризирует содержимое веб-страницы по указанному URL, извлекая краткое содержание и основные выводы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL веб-страницы для саммаризации."
                    }
                },
                "required": ["url"]
            }
        }
    ]

async def summary_webpage(url: str) -> str:
    """
    Саммаризирует содержимое веб-страницы по указанному URL.
    Извлекает текст, затем использует языковую модель для формирования краткого содержания и выводов.
    """
    try:
        # Использование browse_page для получения содержимого страницы
        browse_result = await default_api.browse_page(url=url, output='text')
        
        if not browse_result or "content" not in browse_result or not browse_result["content"]:
            return f"Не удалось получить содержимое страницы по URL: {url}"

        page_text = browse_result["content"]
        
        # Если текст слишком короткий, возможно, страница пуста или не содержит значимого контента
        if len(page_text) < 100: # Произвольный порог, можно настроить
            return f"Страница по URL {url} содержит слишком мало текста для саммаризации."

        # Отправляем текст на саммаризацию в LLM
        # Предполагаем, что default_api имеет метод для вызова LLM напрямую
        # или что саммаризация происходит через общую логику агента.
        # В данном случае, я буду использовать общий чат-комплишн для саммаризации.
        
        # Важно: Здесь предполагается, что LLM-запрос будет выполнен асинхронно
        # и будет использовать текущую активную модель агента для саммаризации.
        # Это не прямой вызов, а скорее декларация того, что текст будет передан LLM.
        
        prompt = f"""Саммаризируй следующий текст веб-страницы, выделив основные идеи и выводы. Ответ должен быть на русском языке.

Текст страницы:
{page_text[:10000]} # Ограничиваем длину текста для LLM, чтобы избежать переполнения контекста

Краткое содержание и выводы:
"""
        # Этот вызов будет обработан основной логикой агента,
        # которая отправит prompt в LLM и вернет результат.
        # В контексте инструмента, я не могу напрямую вызвать LLM для саммаризации,
        # поэтому я должен сделать это через механизм, который предоставит мне среда выполнения.
        # Предположим, что LLM-вызовы по умолчанию доступны через default_api.chat_completion
        
        llm_response = await default_api.chat_completion(
            model="current_agent_model", # Или specific summary model if available
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        
        summary = llm_response.choices[0].message.content if llm_response.choices else "Не удалось получить саммаризацию от LLM."
        
        return summary

    except Exception as e:
        return f"Произошла ошибка при саммаризации веб-страницы {url}: {str(e)}"

