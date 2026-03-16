"""Stage 2: Extract — LLM extraction of structured fields from document chunks."""

from __future__ import annotations

import asyncio
import json
import logging

import anthropic

from config import settings
from models.deal import DealExtraction, ManagementMember
from utils.chunker import Chunk
from prompts.extraction import (
    EXTRACTION_SYSTEM,
    EXTRACTION_TOOL,
    MERGE_SYSTEM,
    extraction_user_prompt,
    merge_user_prompt,
)

logger = logging.getLogger(__name__)


async def call_claude_with_retry(client: anthropic.AsyncAnthropic, **kwargs) -> anthropic.types.Message:
    """Call Claude with exponential backoff retry."""
    for attempt in range(3):
        try:
            return await client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            logger.warning("Rate limited, retrying (attempt %d/3)", attempt + 1)
            await asyncio.sleep(2 ** attempt)
        except anthropic.APITimeoutError:
            logger.warning("API timeout, retrying (attempt %d/3)", attempt + 1)
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("Claude API failed after 3 attempts")


async def extract_chunk(
    client: anthropic.AsyncAnthropic,
    chunk: Chunk,
) -> dict | None:
    """Extract deal data from a single chunk via Claude tool call."""
    try:
        response = await call_claude_with_retry(
            client,
            model=settings.EXTRACTION_MODEL,
            max_tokens=settings.MAX_TOKENS_EXTRACTION,
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": extraction_user_prompt(chunk)}],
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_deal_data"},
        )

        # Extract the tool call input
        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_deal_data":
                logger.info(
                    "Chunk %d/%d extracted — %d fields found",
                    chunk.index + 1,
                    chunk.index + 1,  # Total unknown here, logged at caller
                    sum(1 for v in block.input.values() if v is not None),
                )
                return block.input

        logger.warning("Chunk %d: no tool call in response", chunk.index)
        return None

    except Exception as e:
        logger.error("Chunk %d extraction failed: %s", chunk.index, e)
        return None


async def merge_extractions(
    client: anthropic.AsyncAnthropic,
    partials: list[dict],
) -> DealExtraction:
    """Merge multiple partial extractions into one unified DealExtraction."""
    # Filter out None results
    valid_partials = [p for p in partials if p is not None]

    if not valid_partials:
        logger.warning("No valid partial extractions to merge — returning empty extraction")
        return DealExtraction()

    if len(valid_partials) == 1:
        return _parse_extraction(valid_partials[0])

    partials_json = json.dumps(valid_partials, indent=2)

    response = await call_claude_with_retry(
        client,
        model=settings.EXTRACTION_MODEL,
        max_tokens=8192,
        system=MERGE_SYSTEM,
        messages=[{"role": "user", "content": merge_user_prompt(partials_json)}],
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_deal_data"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_deal_data":
            return _parse_extraction(block.input)

    logger.warning("Merge call returned no tool use — using first partial")
    return _parse_extraction(valid_partials[0])


def _parse_extraction(data: dict) -> DealExtraction:
    """Parse a raw extraction dict into a DealExtraction model."""
    # Handle management_team as list of dicts
    if "management_team" in data and data["management_team"]:
        data["management_team"] = [
            ManagementMember(**m) if isinstance(m, dict) else m
            for m in data["management_team"]
        ]
    return DealExtraction(**data)


async def extract(chunks: list[Chunk]) -> tuple[DealExtraction, int]:
    """Run map-reduce extraction across all chunks.

    Returns:
        Tuple of (DealExtraction, total_tokens_used)
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Map: extract from each chunk in parallel
    logger.info("Extracting from %d chunks", len(chunks))
    partials = await asyncio.gather(*[
        extract_chunk(client, chunk) for chunk in chunks
    ])

    # Reduce: merge all partials
    logger.info("Merging %d partial extractions", len([p for p in partials if p]))
    merged = await merge_extractions(client, list(partials))

    # Approximate token usage (not exact without response metadata aggregation)
    tokens_used = sum(c.token_count for c in chunks) + 2000  # rough estimate

    return merged, tokens_used
