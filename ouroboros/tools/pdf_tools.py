"""
PDF reading tools for Ouroboros.

Provides:
  - pdf_read: extract text from a PDF file (Drive or repo path)
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# pdfplumber will be installed at runtime. Import lazily in the handler to fail gracefully if missing.
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None
    PDFPLUMBER_AVAILABLE = False


def _resolve_file_path(path: str) -> pathlib.Path:
    """
    Resolve a user-provided path to an existing file.

    Search order:
      1. Absolute path (if exists)
      2. Relative to current working directory (repo root)
      3. Relative to DRIVE_ROOT (Google Drive mount)
    Raises FileNotFoundError if not found.
    """
    # Import here to avoid circular import issues; state module does not depend on tools.
    from supervisor.state import DRIVE_ROOT

    p = pathlib.Path(path)

    if p.is_absolute():
        if p.exists():
            return p
        raise FileNotFoundError(f"File not found at absolute path: {path}")

    # Try relative to cwd (repo root)
    cwd = pathlib.Path.cwd()
    candidate = cwd / p
    if candidate.exists():
        return candidate

    # Try relative to DRIVE_ROOT
    drive_candidate = DRIVE_ROOT / p
    if drive_candidate.exists():
        return drive_candidate

    raise FileNotFoundError(f"File not found: {path} (checked repo root and Drive root)")


def _pdf_read(ctx: ToolContext, path: str, max_pages: int = 0) -> str:
    """
    Read a PDF file and extract its text content.

    Parameters:
      path: Path to PDF file. Can be:
        - absolute path
        - relative to repository root
        - relative to Google Drive root (MyDrive/Ouroboros/)
      max_pages: Maximum number of pages to extract (0 = all pages)

    Returns:
      Extracted text as a string, or an error description if extraction fails.
    """
    if not PDFPLUMBER_AVAILABLE:
        return "⚠️ pdfplumber is not installed. Run: pip install pdfplumber"

    if not path.endswith(".pdf"):
        return "⚠️ Only PDF files are supported. Provide a path ending with .pdf"

    try:
        file_path = _resolve_file_path(path)
    except FileNotFoundError as e:
        return f"⚠️ {e}"

    try:
        text_parts: List[str] = []
        with pdfplumber.open(file_path) as pdf:
            pages = pdf.pages
            if max_pages > 0:
                pages = pages[:max_pages]
            for i, page in enumerate(pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                else:
                    log.debug("Page %d extracted no text (possibly image-only)", i)
        full_text = "\n".join(text_parts)
        if not full_text.strip():
            return "⚠️ PDF contained no extractable text (may be image-only or encrypted)."
        return full_text
    except Exception as e:
        log.warning("PDF extraction failed for %s: %s", path, e, exc_info=True)
        return f"⚠️ Failed to extract text from PDF: {e}"


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            name="pdf_read",
            schema={
                "name": "pdf_read",
                "description": (
                    "Read a PDF file and extract its text content. "
                    "Supports paths relative to repository root or Google Drive root. "
                    "Uses pdfplumber under the hood to extract text from pages."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to PDF file (absolute, or relative to repo/Drive)",
                        },
                        "max_pages": {
                            "type": "integer",
                            "description": "Maximum number of pages to extract (0 = all)",
                            "default": 0,
                        },
                    },
                    "required": ["path"],
                },
            },
            handler=_pdf_read,
            timeout_sec=60,  # PDF extraction can be slow for large files
        ),
    ]
