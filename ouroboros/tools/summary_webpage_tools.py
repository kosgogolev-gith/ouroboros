from typing import Literal
from . import llm

def summary_webpage(url: str) -> str:
    """
    Делает саммаризацию страницы по ссылке: краткое содержание и вывод.

    Args:
        url: URL страницы для саммаризации.

    Returns:
        Текст с саммаризацией страницы: краткое содержание и вывод.
    """
    # TODO: Implement actual webpage browsing and summarization
    return f"Суммаризация страницы по ссылке: {url} пока не реализована."

def get_tools():
    return [
        summary_webpage,
    ]
