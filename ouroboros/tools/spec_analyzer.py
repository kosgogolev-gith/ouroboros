"""Spec analyzer tool: compare technical offers against requirements."""

from __future__ import annotations

import logging
from typing import List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)


def _spec_compare(
    ctx: ToolContext,
    *,
    vendor_file: str,
    baseline_topic: str,
    vendor_sheet: Optional[str] = None,
    requirements_text: Optional[str] = None,
) -> str:
    """Compare a technical offer against baseline requirements.

    This tool loads baseline requirements from the knowledge base and parses
    the vendor's Excel or PDF file, then produces a structured prompt for the
    LLM to generate a compliance analysis.

    Args:
        vendor_file: Path to the vendor's commercial offer (XLSX or PDF).
        baseline_topic: Knowledge base topic containing the requirements (e.g., 'requirements-h200', 'requirements-b200x8').
        vendor_sheet: For XLSX files, the specific sheet to read (default: first sheet).
        requirements_text: Optional pre-loaded requirements text. If provided, baseline_topic is ignored.

    Returns:
        A structured analysis prompt that the LLM should complete to produce
        the compliance matrix, critical deviations, and commercial summary.
    """
    # Step 1: Get requirements text either from argument or from knowledge base
    if requirements_text is None:
        # Read from knowledge base via Drive (knowledge topics stored in memory/knowledge/)
        # The knowledge files are Markdown; we need to read them from Drive.
        knowledge_path = f"memory/knowledge/{baseline_topic}.md"
        try:
            requirements_text = ctx.drive_path(knowledge_path).read_text(encoding="utf-8")
        except Exception as e:
            return f"⚠️ Failed to read knowledge base topic '{baseline_topic}': {e}"
    else:
        requirements_text = requirements_text[:10000]  # truncate for safety

    # Step 2: Parse vendor file
    vendor_text = ""
    file_lower = vendor_file.lower()
    try:
        if file_lower.endswith(".xlsx"):
            # Use xlsx_read tool logic directly to avoid circular tool call
            # We'll implement a simple xlsx reader fallback if we can't import
            try:
                import openpyxl
                wb = openpyxl.load_workbook(vendor_file, data_only=True, read_only=True)
                if vendor_sheet:
                    ws = wb[vendor_sheet] if vendor_sheet in wb.sheetnames else wb.active
                else:
                    ws = wb.active
                lines = []
                for row in ws.iter_rows(values_only=True):
                    line = "\t".join(str(cell) if cell is not None else "" for cell in row)
                    lines.append(line)
                vendor_text = "\n".join(lines)
            except ImportError:
                return "⚠️ openpyxl not available; cannot read XLSX. Install openpyxl."
        elif file_lower.endswith(".pdf"):
            # PDF reading requires additional tool; we cannot implement fallback easily.
            return "⚠️ PDF parsing not directly available in spec_compare. Please use pdf_read first and pass the extracted text as requirements_text/offer_text."
        else:
            # Assume plain text
            vendor_text = ctx.drive_path(vendor_file).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"⚠️ Failed to read vendor file '{vendor_file}': {e}"

    if not vendor_text.strip():
        return "⚠️ Vendor file appears empty after parsing."

    # Truncate vendor text for safety
    vendor_text = vendor_text[:20000]

    # Step 3: Construct the structured analysis prompt
    prompt = f"""## Задание: Анализ соответствия КП требованиям ТЗ

### Требования (ТЗ) из базиса `{baseline_topic}`:
```
{requirements_text}
```

### Коммерческое предложение (КП):
```
{vendor_text}
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
- Какие параметры требуют дополнительной проверки

Верни результат в формате Markdown."""

    return prompt


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            name="spec_compare",
            schema={
                "name": "spec_compare",
                "description": (
                    "Compare a vendor's commercial offer against baseline requirements. "
                    "Loads baseline from knowledge base (e.g., 'requirements-h200') and "
                    "parses the vendor's Excel file. Returns a structured prompt for the LLM "
                    "to generate a compliance matrix, flag deviations, and summarize commercial terms."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vendor_file": {
                            "type": "string",
                            "description": "Path to the vendor's Excel or PDF file (on Drive or local).",
                        },
                        "baseline_topic": {
                            "type": "string",
                            "description": "Knowledge base topic with baseline requirements (e.g., 'requirements-h200', 'requirements-b200x8').",
                        },
                        "vendor_sheet": {
                            "type": "string",
                            "description": "For XLSX files, the sheet name to read (default: first sheet).",
                        },
                        "requirements_text": {
                            "type": "string",
                            "description": "Pre-loaded requirements text; if given, baseline_topic is ignored.",
                        },
                    },
                    "required": ["vendor_file", "baseline_topic"],
                },
            },
            handler=_spec_compare,
            is_code_tool=False,
            timeout_sec=180,
        ),
    ]
