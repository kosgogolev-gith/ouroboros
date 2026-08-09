"""PDF tools for Ouroboros — extract text via pymupdf, analyze via document_analyze."""
import base64
import logging
import os
import pathlib
import tempfile
from typing import List, Optional

log = logging.getLogger(__name__)

try:
    from ouroboros.tools.registry import ToolEntry
except ImportError:
    ToolEntry = None


def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = 50) -> str:
    """Extract text from PDF bytes using pymupdf."""
    import pymupdf
    text_parts = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        total = len(doc)
        meta = doc.metadata or {}
        if meta.get("title"):
            text_parts.append(f"# {meta['title']}")
        if meta.get("author"):
            text_parts.append(f"Автор: {meta['author']}")
        text_parts.append(f"Страниц: {total}")
        text_parts.append("---")

        pages_to_read = min(total, max_pages)
        for i in range(pages_to_read):
            page = doc[i]
            page_text = page.get_text("text").strip()
            if page_text:
                text_parts.append(f"\n[Стр. {i+1}]\n{page_text}")

        if total > max_pages:
            text_parts.append(f"\n[...ещё {total - max_pages} стр. обрезано]")

    return "\n".join(text_parts)


def _pdf_read(ctx, file_path: str = "", pdf_base64: str = "",
              max_pages: int = 50) -> str:
    """Extract text from a PDF file (by path or base64)."""
    try:
        if pdf_base64:
            pdf_bytes = base64.b64decode(pdf_base64)
        elif file_path:
            p = pathlib.Path(file_path).expanduser()
            if not p.exists():
                return f"❌ Файл не найден: {file_path}"
            pdf_bytes = p.read_bytes()
        else:
            return "❌ Укажи file_path или pdf_base64"

        text = _extract_pdf_text(pdf_bytes, max_pages=max_pages)
        return text if text else "❌ PDF не содержит текста (возможно, сканированный — попробуй pdf_analyze_scan)"
    except Exception as e:
        return f"❌ Ошибка чтения PDF: {e}"


def _pdf_analyze(ctx, file_path: str = "", pdf_base64: str = "",
                 mode: str = "analyze", task: str = "",
                 max_pages: int = 30) -> str:
    """Extract text from PDF and analyze via Perplexity sonar-reasoning-pro.

    mode: analyze | summarize | extract | compare | risks | tco
    """
    try:
        if pdf_base64:
            pdf_bytes = base64.b64decode(pdf_base64)
        elif file_path:
            p = pathlib.Path(file_path).expanduser()
            if not p.exists():
                return f"❌ Файл не найден: {file_path}"
            pdf_bytes = p.read_bytes()
        else:
            return "❌ Укажи file_path или pdf_base64"

        # Extract text
        text = _extract_pdf_text(pdf_bytes, max_pages=max_pages)
        if not text or len(text) < 50:
            return "❌ PDF не содержит достаточно текста для анализа"

        # Analyze via document_analyze
        from ouroboros.tools.search import _document_analyze
        result = _document_analyze(ctx, document_text=text, mode=mode, task=task)
        return result

    except Exception as e:
        return f"❌ Ошибка анализа PDF: {e}"


def _pdf_metadata(ctx, file_path: str = "", pdf_base64: str = "") -> str:
    """Get PDF metadata: title, author, pages, creation date."""
    try:
        if pdf_base64:
            pdf_bytes = base64.b64decode(pdf_base64)
        elif file_path:
            p = pathlib.Path(file_path).expanduser()
            pdf_bytes = p.read_bytes()
        else:
            return "❌ Укажи file_path или pdf_base64"

        import pymupdf
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            meta = doc.metadata or {}
            lines = [
                f"📄 **PDF Метаданные**",
                f"Страниц: {len(doc)}",
            ]
            for key, label in [("title","Название"),("author","Автор"),
                                ("subject","Тема"),("creator","Создано в"),
                                ("creationDate","Дата создания")]:
                val = meta.get(key,"").strip()
                if val:
                    lines.append(f"{label}: {val}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка: {e}"


def get_tools() -> List:
    if ToolEntry is None:
        return []
    return [
        ToolEntry(
            "pdf_read",
            {
                "name": "pdf_read",
                "description": "Extract text from a PDF file. Provide file_path (local path) or pdf_base64. Returns full text by pages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Local file path to PDF", "default": ""},
                        "pdf_base64": {"type": "string", "description": "Base64-encoded PDF bytes", "default": ""},
                        "max_pages": {"type": "integer", "description": "Max pages to extract (default 50)", "default": 50},
                    },
                    "required": [],
                },
            },
            _pdf_read,
        ),
        ToolEntry(
            "pdf_analyze",
            {
                "name": "pdf_analyze",
                "description": (
                    "Extract text from PDF and analyze via AI (sonar-reasoning-pro). "
                    "Best for: КП, contracts, specs, reports. "
                    "Modes: analyze, summarize, extract, compare, risks, tco. "
                    "Provide file_path or pdf_base64."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "default": ""},
                        "pdf_base64": {"type": "string", "default": ""},
                        "mode": {
                            "type": "string",
                            "enum": ["analyze", "summarize", "extract", "compare", "risks", "tco"],
                            "default": "analyze",
                        },
                        "task": {"type": "string", "description": "Specific focus (e.g. 'найди риски в гарантийных условиях')", "default": ""},
                        "max_pages": {"type": "integer", "default": 30},
                    },
                    "required": [],
                },
            },
            _pdf_analyze,
        ),
        ToolEntry(
            "pdf_metadata",
            {
                "name": "pdf_metadata",
                "description": "Get PDF metadata: title, author, page count, creation date.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "default": ""},
                        "pdf_base64": {"type": "string", "default": ""},
                    },
                    "required": [],
                },
            },
            _pdf_metadata,
        ),
    ]
