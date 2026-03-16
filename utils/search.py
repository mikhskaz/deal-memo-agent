"""Tavily web search client wrapper."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavily import TavilyClient

from models.deal import SearchResult

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)

_client: TavilyClient | None = None


def _get_client(api_key: str) -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=api_key)
    return _client


async def search(
    query: str,
    api_key: str,
    max_results: int = 3,
) -> list[SearchResult]:
    """Execute a single search query via Tavily and return structured results."""
    client = _get_client(api_key)

    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
        )
    except Exception as e:
        logger.error("Tavily search failed for query '%s': %s", query, e)
        return []

    results = [
        SearchResult(
            query=query,
            url=r["url"],
            title=r["title"],
            content=r["content"],
        )
        for r in response.get("results", [])
    ]

    logger.info("Search '%s' returned %d results", query, len(results))
    return results
