"""Token-aware text chunking using tiktoken."""

from __future__ import annotations

import logging

import tiktoken

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Use cl100k_base encoding (same as GPT-4 / Claude tokenizer approximation)
_encoder = tiktoken.get_encoding("cl100k_base")


class Chunk(BaseModel):
    index: int
    page_range: tuple[int, int]
    token_count: int
    text: str


def count_tokens(text: str) -> int:
    """Count tokens in a string."""
    return len(_encoder.encode(text))


def chunk_pages(
    pages: list[dict],
    chunk_size_tokens: int = 6000,
    chunk_overlap_tokens: int = 500,
) -> list[Chunk]:
    """Split page texts into token-aware chunks with overlap.

    Args:
        pages: List of dicts with 'page_num' and 'text' keys.
        chunk_size_tokens: Target token count per chunk.
        chunk_overlap_tokens: Token overlap between consecutive chunks.

    Returns:
        List of Chunk objects with index, page_range, token_count, and text.
    """
    # Build a list of (page_num, paragraph) pairs preserving paragraph boundaries
    segments: list[tuple[int, str]] = []
    for page in pages:
        paragraphs = page["text"].split("\n\n")
        for para in paragraphs:
            para = para.strip()
            if para:
                segments.append((page["page_num"], para))

    if not segments:
        return []

    chunks: list[Chunk] = []
    current_texts: list[str] = []
    current_tokens = 0
    current_pages: list[int] = []
    chunk_index = 0

    for page_num, para in segments:
        para_tokens = count_tokens(para)

        # If a single paragraph exceeds chunk size, force it into its own chunk
        if para_tokens > chunk_size_tokens:
            # Flush current buffer first
            if current_texts:
                text = "\n\n".join(current_texts)
                chunks.append(Chunk(
                    index=chunk_index,
                    page_range=(min(current_pages), max(current_pages)),
                    token_count=count_tokens(text),
                    text=text,
                ))
                chunk_index += 1
                current_texts = []
                current_tokens = 0
                current_pages = []

            # Add oversized paragraph as its own chunk
            chunks.append(Chunk(
                index=chunk_index,
                page_range=(page_num, page_num),
                token_count=para_tokens,
                text=para,
            ))
            chunk_index += 1
            continue

        # Would adding this paragraph exceed chunk size?
        if current_tokens + para_tokens > chunk_size_tokens and current_texts:
            # Flush current chunk
            text = "\n\n".join(current_texts)
            chunks.append(Chunk(
                index=chunk_index,
                page_range=(min(current_pages), max(current_pages)),
                token_count=count_tokens(text),
                text=text,
            ))
            chunk_index += 1

            # Build overlap: take trailing paragraphs that fit in overlap budget
            overlap_texts: list[str] = []
            overlap_tokens = 0
            for t in reversed(current_texts):
                t_tokens = count_tokens(t)
                if overlap_tokens + t_tokens > chunk_overlap_tokens:
                    break
                overlap_texts.insert(0, t)
                overlap_tokens += t_tokens

            current_texts = overlap_texts
            current_tokens = overlap_tokens
            # Keep page tracking from overlap segments
            current_pages = [current_pages[-1]] if current_pages else []

        current_texts.append(para)
        current_tokens += para_tokens
        if page_num not in current_pages:
            current_pages.append(page_num)

    # Flush remaining
    if current_texts:
        text = "\n\n".join(current_texts)
        chunks.append(Chunk(
            index=chunk_index,
            page_range=(min(current_pages), max(current_pages)),
            token_count=count_tokens(text),
            text=text,
        ))

    logger.info(
        "Created %d chunks from %d pages (%d total tokens)",
        len(chunks),
        len(pages),
        sum(c.token_count for c in chunks),
    )
    return chunks
