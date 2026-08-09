from typing import List
from ..agent import Agent  # Импорт Agent для использования LLM

def get_tools() -> List[dict]:
    """
    Возвращает список инструментов, предоставляемых этим модулем.
    """
    return [
        {
            "name": "summary_webpage",
            "description": "Делает саммаризацию страницы по ссылке: краткое содержание и вывод.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL страницы для саммаризации."
                    },
                },
                "required": ["url"],
            },
        }
    ]

def summary_webpage(url: str) -> str:
    """
    Делает саммаризацию страницы по ссылке: краткое содержание и вывод.

    Args:
        url (str): URL страницы для саммаризации.

    Returns:
        str: Текст с саммаризацией страницы: краткое содержание и вывод.
    """
    # Здесь будет реализована логика получения содержимого страницы и ее саммаризации
    # Пока заглушка
    return f"Саммаризация страницы по ссылке {url} пока не реализована."
