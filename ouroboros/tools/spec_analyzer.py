"""Spec analyzer tool: compare technical offers against requirements."""

from __future__ import annotations

import logging
from typing import List

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)


def _spec_compare(ctx: ToolContext, requirements_text: str, offer_text: str) -> str:
    """Compare technical offer against requirements.

    Does not call an LLM directly — instead, formats a structured prompt
    that the main model will use to produce the compliance analysis.

    Args:
        requirements_text: Extracted text from the requirements/TZ document.
        offer_text: Extracted text from the commercial offer/KP document.

    Returns:
        A structured analysis prompt with both texts and a template for the model to fill.
    """
    template = f"""## Задание: Анализ соответствия КП требованиям ТЗ

### Требования (ТЗ):
```
{requirements_text}
```

### Коммерческое предложение (КП):
```
{offer_text}
```

### Инструкция по анализу:

Сравни КП с требованиями ТЗ и заполни следующую структуру:

**Резюме:** [соответствует / частично соответствует / не соответствует] — одна строка с обоснованием.

**Таблица соответствия:**

| Параметр | Требование (ТЗ) | Факт (КП) | Статус |
|----------|-----------------|-----------|--------|
| ... | ... | ... | ✅/⚠️/❌ |

Правила оценки:
- ✅ — параметр полностью соответствует или превышает требование
- ⚠️ — параметр близок к требованию, но есть отклонения или неясности
- ❌ — параметр не соответствует требованию или отсутствует в КП

**Критические несоответствия:**
- Перечисли все параметры со статусом ❌ с пояснением

**Коммерческие условия:**
- Цена (за единицу / за систему / FOB)
- Срок поставки
- Гарантия
- MOQ (минимальный заказ)
- Условия оплаты

**Рекомендации:**
- Что нужно уточнить у поставщика
- Какие параметры требуют дополнительной проверки"""

    return template


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("spec_compare", {
            "name": "spec_compare",
            "description": (
                "Compare a technical offer (KP) against requirements (TZ). "
                "Takes requirements text and offer text, returns a structured "
                "analysis prompt with compliance table template. "
                "The main model fills in the actual comparison."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements_text": {
                        "type": "string",
                        "description": (
                            "Text extracted from the requirements/TZ document."
                        ),
                    },
                    "offer_text": {
                        "type": "string",
                        "description": (
                            "Text extracted from the commercial offer/KP document."
                        ),
                    },
                    "requirements_sheet": {
                        "type": "string",
                        "description": (
                            "Name of the specific worksheet to extract requirements from."
                        ),
                    },
                },
                "required": ["requirements_text", "offer_text"],
            },
        }, _spec_compare),
    ]
