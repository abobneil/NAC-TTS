from __future__ import annotations

from pathlib import Path

import fitz

from .text_utils import normalize_text


class PdfValidationError(ValueError):
    pass


def extract_text_from_pdf(path: Path, max_pages: int) -> tuple[str, int]:
    with fitz.open(path) as document:
        if document.needs_pass:
            raise PdfValidationError("Encrypted PDFs are not supported in v1.")

        page_count = document.page_count
        if page_count > max_pages:
            raise PdfValidationError(f"PDF exceeds the page limit of {max_pages}.")

        pages_with_text = 0
        parts: list[str] = []
        for page in document:
            text = normalize_text(page.get_text("text"))
            if text:
                pages_with_text += 1
                parts.append(text)

        if pages_with_text == 0:
            raise PdfValidationError("OCR is not supported yet. Upload a text-based PDF.")

        return "\n\n".join(parts), page_count
