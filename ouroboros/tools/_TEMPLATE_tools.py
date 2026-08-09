"""
ШАБЛОН нового инструмента для Ouroboros.
Скопируй этот файл, замени MY_TOOL на имя инструмента.
Файл ОБЯЗАТЕЛЬНО должен называться *_tools.py (суффикс _tools).
"""
from typing import List
from ouroboros.tools.registry import ToolEntry


def _my_tool_handler(ctx, param1: str, param2: str = "default") -> str:
    """Основная логика инструмента."""
    try:
        # Твой код здесь
        result = f"OK: {param1}, {param2}"
        return result
    except Exception as e:
        return f"❌ Ошибка: {e}"


def get_tools() -> List[ToolEntry]:
    """ОБЯЗАТЕЛЬНО: реестр вызывает эту функцию при старте."""
    return [
        ToolEntry(
            "my_tool",                          # Имя инструмента (без пробелов)
            {
                "name": "my_tool",
                "description": "Краткое описание что делает инструмент.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {
                            "type": "string",
                            "description": "Описание параметра"
                        },
                        "param2": {
                            "type": "string",
                            "description": "Опциональный параметр",
                            "default": "default"
                        },
                    },
                    "required": ["param1"],     # Обязательные параметры
                },
            },
            _my_tool_handler,                   # Ссылка на функцию-обработчик
        )
    ]
