"""PDF-to-text extraction with table detection."""

from __future__ import annotations

import io
import logging

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)


def _extract_tables_as_markdown(page: pdfplumber.page.Page) -> str:
    """Extract tables from a pdfplumber page and format as markdown."""
    tables = page.extract_tables()
    if not tables:
        return ""

    md_parts: list[str] = []
    for table in tables:
        if not table or not table[0]:
            continue
        # Header row
        headers = [str(cell or "").strip() for cell in table[0]]
        md_parts.append("| " + " | ".join(headers) + " |")
        md_parts.append("| " + " | ".join("---" for _ in headers) + " |")
        # Data rows
        for row in table[1:]:
            cells = [str(cell or "").strip() for cell in row]
            # Pad or truncate to match header count
            while len(cells) < len(headers):
                cells.append("")
            cells = cells[: len(headers)]
            md_parts.append("| " + " | ".join(cells) + " |")
        md_parts.append("")

    return "\n".join(md_parts)


def extract_text_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """Extract text from PDF bytes, returning a list of page dicts.

    Each dict has:
        - page_num: int (1-indexed)
        - text: str (the page text, with tables prepended as markdown)

    Strategy:
        1. Try pdfplumber first for table-rich pages
        2. Fall back to PyMuPDF for layout-heavy pages
    """
    pages: list[dict] = []

    # Extract with pdfplumber (good for tables)
    plumber_pages: dict[int, dict] = {}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_num = i + 1
                table_md = _extract_tables_as_markdown(page)
                text = page.extract_text() or ""
                plumber_pages[page_num] = {
                    "text": text,
                    "table_md": table_md,
                    "has_tables": bool(table_md),
                }
    except Exception as e:
        logger.warning("pdfplumber failed: %s — falling back to PyMuPDF only", e)

    # Extract with PyMuPDF (good for layout)
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i, page in enumerate(doc):
            page_num = i + 1
            mu_text = page.get_text("text") or ""

            plumber_data = plumber_pages.get(page_num)

            if plumber_data and plumber_data["has_tables"]:
                # Prefer pdfplumber text when tables are present, prepend table markdown
                page_text = plumber_data["table_md"] + "\n" + plumber_data["text"]
            elif plumber_data and len(plumber_data["text"]) > len(mu_text):
                # Use whichever extracted more text
                page_text = plumber_data["text"]
            else:
                page_text = mu_text

            pages.append({"page_num": page_num, "text": page_text.strip()})

        doc.close()
    except Exception as e:
        logger.error("PyMuPDF failed: %s", e)
        # Fall back to pdfplumber-only results
        if plumber_pages:
            for page_num in sorted(plumber_pages.keys()):
                data = plumber_pages[page_num]
                text = data["table_md"] + "\n" + data["text"] if data["has_tables"] else data["text"]
                pages.append({"page_num": page_num, "text": text.strip()})
        else:
            raise RuntimeError("Both PDF parsers failed") from e

    total_chars = sum(len(p["text"]) for p in pages)
    non_empty = sum(1 for p in pages if len(p["text"]) > 50)
    logger.info(
        "Extracted %d pages from PDF (%d chars total, %d non-empty pages)",
        len(pages), total_chars, non_empty,
    )
    return pages
