"""Stage 3: Enrich — Web search for comps, news, and sector intelligence."""

from __future__ import annotations

import asyncio
import json
import logging

import anthropic

from config import settings
from models.deal import DealExtraction, DealEnrichment, SearchResult
from prompts.enrichment import (
    QUERY_GENERATION_SYSTEM,
    SUMMARIZE_SYSTEM,
    SUMMARIZE_TOOL,
    query_generation_prompt,
    summarize_prompt,
)
from utils.search import search
from pipeline.extract import call_claude_with_retry

logger = logging.getLogger(__name__)


async def generate_search_queries(
    client: anthropic.AsyncAnthropic,
    extraction: DealExtraction,
) -> list[str]:
    """Use Claude to generate targeted search queries from the extraction."""
    response = await call_claude_with_retry(
        client,
        model=settings.EXTRACTION_MODEL,
        max_tokens=1024,
        system=QUERY_GENERATION_SYSTEM,
        messages=[{
            "role": "user",
            "content": query_generation_prompt(extraction, settings.MAX_SEARCH_QUERIES),
        }],
    )

    # Parse the JSON array from response text
    text = response.content[0].text.strip()

    # Handle cases where Claude wraps in markdown code blocks
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        queries = json.loads(text)
        if isinstance(queries, list):
            queries = [q for q in queries if isinstance(q, str)][:settings.MAX_SEARCH_QUERIES]
            logger.info("Generated %d search queries", len(queries))
            return queries
    except json.JSONDecodeError:
        logger.error("Failed to parse search queries from Claude response: %s", text[:200])

    # Fallback: generate basic queries from extraction
    fallback = []
    if extraction.company_name:
        fallback.append(f"{extraction.company_name} news")
    if extraction.sector:
        fallback.append(f"{extraction.sector} M&A transactions 2024 2025")
        fallback.append(f"{extraction.sector} EV/Revenue multiples")
    logger.warning("Using %d fallback queries", len(fallback))
    return fallback


async def summarize_search_results(
    client: anthropic.AsyncAnthropic,
    extraction: DealExtraction,
    all_results: list[SearchResult],
) -> DealEnrichment:
    """Use Claude to summarize search results into enrichment categories."""
    if not all_results:
        logger.warning("No search results to summarize — returning empty enrichment")
        return DealEnrichment(sources=[])

    results_json = json.dumps(
        [r.model_dump() for r in all_results],
        indent=2,
    )

    response = await call_claude_with_retry(
        client,
        model=settings.EXTRACTION_MODEL,
        max_tokens=4096,
        system=SUMMARIZE_SYSTEM,
        messages=[{
            "role": "user",
            "content": summarize_prompt(extraction, results_json),
        }],
        tools=[SUMMARIZE_TOOL],
        tool_choice={"type": "tool", "name": "summarize_enrichment"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "summarize_enrichment":
            return DealEnrichment(
                **block.input,
                sources=all_results,
            )

    logger.warning("Summarize call returned no tool use — returning raw sources only")
    return DealEnrichment(sources=all_results)


async def enrich(extraction: DealExtraction) -> tuple[DealEnrichment, int]:
    """Run the enrichment pipeline: generate queries, search, summarize.

    Returns:
        Tuple of (DealEnrichment, total_tokens_used)
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # 1. Generate search queries
    queries = await generate_search_queries(client, extraction)
    logger.info("Generated %d queries, executing in parallel", len(queries))

    # 2. Execute all queries in parallel
    search_tasks = [
        search(q, settings.TAVILY_API_KEY, settings.MAX_SEARCH_RESULTS_PER_QUERY)
        for q in queries
    ]
    results_lists = await asyncio.gather(*search_tasks)

    # Flatten results
    all_results: list[SearchResult] = []
    for result_list in results_lists:
        all_results.extend(result_list)

    logger.info("Search complete — %d results across %d queries", len(all_results), len(queries))

    # 3. Summarize results
    enrichment = await summarize_search_results(client, extraction, all_results)

    tokens_used = 3000  # rough estimate for query gen + summarization
    return enrichment, tokens_used
