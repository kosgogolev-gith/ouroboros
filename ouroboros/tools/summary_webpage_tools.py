from typing import Optional

from pydantic import BaseModel, Field

from .registry import register_tool
from ..utils import get_llm

class SummaryWebpageArgs(BaseModel):
    url: str = Field(..., description="URL страницы для саммаризации")

@register_tool
def summary_webpage(args: SummaryWebpageArgs) -> str:
    """
    Делает саммаризацию страницы по ссылке: краткое содержание и вывод.
    """
    return "Функция summary_webpage пока не реализована."
