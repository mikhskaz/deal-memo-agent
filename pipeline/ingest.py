"""Stage 1: Ingest — Convert PDF bytes to text chunks."""

from __future__ import annotations

import logging

from config import settings
from utils.pdf import extract_text_from_pdf
from utils.chunker import Chunk, chunk_pages

logger = logging.getLogger(__name__)


async def ingest(pdf_bytes: bytes) -> list[Chunk]:
    """Parse a PDF and split into token-aware chunks.

    1. Extract text from PDF (pdfplumber + PyMuPDF)
    2. Split into chunks using tiktoken
    3. Tag each chunk with index, page_range, token_count
    """
    pages = extract_text_from_pdf(pdf_bytes)

    if not pages:
        raise RuntimeError("PDF produced no extractable text — it may be a scanned image PDF")

    total_text_len = sum(len(p["text"]) for p in pages)
    logger.info("Total extracted text: %d chars across %d pages", total_text_len, len(pages))
    if total_text_len < 100:
        raise RuntimeError(
            f"PDF text extraction yielded very little text ({total_text_len} chars "
            f"across {len(pages)} pages) — the document may be image-based or corrupted"
        )

    chunks = chunk_pages(
        pages,
        chunk_size_tokens=settings.CHUNK_SIZE_TOKENS,
        chunk_overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
    )

    logger.info(
        "Parsed %d pages, created %d chunks (%d tokens total)",
        len(pages),
        len(chunks),
        sum(c.token_count for c in chunks),
    )

    return chunks
