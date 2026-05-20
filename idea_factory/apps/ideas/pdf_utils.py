"""Extract plain text from PDF files for LLM context."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_EXTRACTED_CHARS = 50_000


def extract_text_from_pdf(file_path: str | Path) -> str:
    """
    Extract text from a PDF file. Returns empty string on failure.
    Output is truncated to MAX_EXTRACTED_CHARS.
    """
    path = Path(file_path)
    if not path.is_file():
        return ""

    try:
        from pypdf import PdfReader
    except ImportError:
        logger.error("pypdf is not installed; cannot extract PDF text")
        return ""

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        combined = "\n\n".join(parts).strip()
        if len(combined) > MAX_EXTRACTED_CHARS:
            combined = combined[:MAX_EXTRACTED_CHARS] + "\n...[truncated]"
        return combined
    except Exception:
        logger.exception("Failed to extract text from PDF: %s", path)
        return ""
