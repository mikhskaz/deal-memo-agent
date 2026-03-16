"""Stage 4: Draft — LLM synthesis of memo sections."""

from __future__ import annotations

import asyncio
import logging

import anthropic

from config import settings
from models.deal import DealExtraction, DealEnrichment, Memo, MemoSection
from prompts.drafting import DRAFTING_SYSTEM, SECTION_PROMPTS, section_prompt
from pipeline.extract import call_claude_with_retry
from datetime import datetime

logger = logging.getLogger(__name__)

SECTIONS = [
    "executive_summary",
    "business_description",
    "market_opportunity",
    "financial_overview",
    "key_risks",
    "management_team",
    "diligence_questions",
    "recommended_next_step",
]


async def draft_section(
    client: anthropic.AsyncAnthropic,
    section_name: str,
    extraction: DealExtraction,
    enrichment: DealEnrichment,
) -> MemoSection:
    """Draft a single memo section via Claude."""
    prompt = section_prompt(section_name, extraction, enrichment)

    response = await call_claude_with_retry(
        client,
        model=settings.DRAFTING_MODEL,
        max_tokens=settings.MAX_TOKENS_DRAFT,
        system=DRAFTING_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    content = response.content[0].text.strip()
    word_count = len(content.split())

    logger.info("Section %s drafted — %d words", section_name, word_count)

    return MemoSection(
        section_id=section_name,
        content=content,
        word_count=word_count,
    )


async def draft(
    extraction: DealExtraction,
    enrichment: DealEnrichment,
) -> tuple[Memo, int]:
    """Draft all memo sections in parallel.

    Returns:
        Tuple of (Memo, total_tokens_used)
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Drafting %d sections", len(SECTIONS))

    section_results = await asyncio.gather(*[
        draft_section(client, section_name, extraction, enrichment)
        for section_name in SECTIONS
    ])

    sections = dict(zip(SECTIONS, section_results))

    memo = Memo(
        sections=sections,
        generated_at=datetime.utcnow(),
        model_used=settings.DRAFTING_MODEL,
        total_tokens_used=0,  # Will be updated by orchestrator
    )

    total_words = sum(s.word_count for s in section_results)
    tokens_used = total_words * 2  # rough estimate

    logger.info("All sections drafted — %d total words", total_words)

    return memo, tokens_used
