"""Prompt templates for web search query generation and result summarization."""

from __future__ import annotations

from models.deal import DealExtraction


QUERY_GENERATION_SYSTEM = """You are a buy-side investment analyst preparing to research a deal. \
Generate targeted web search queries to gather the intelligence needed for an \
investment memo. Return a JSON array of query strings. No explanation, just the array."""


def query_generation_prompt(extraction: DealExtraction, max_queries: int = 6) -> str:
    return f"""Based on the following deal summary, generate up to {max_queries} targeted \
web search queries to gather the intelligence needed for an investment memo.

Deal summary:
{extraction.model_dump_json(indent=2)}

Generate queries for:
1. Comparable public company EV/Revenue and EV/EBITDA multiples in this sector
2. Recent private M&A transactions in this sector (last 24 months)
3. Recent news about this specific company
4. Key competitors and market share
5. Sector macro trends, tailwinds, and regulatory context
6. Background on the CEO / founder if named

Return a JSON array of query strings. No explanation, just the array."""


SUMMARIZE_SYSTEM = """You are a senior investment analyst. Summarize web search results \
into structured intelligence categories for an investment memo. \
Be factual and cite specific data points. If information is limited, say so explicitly."""


def summarize_prompt(extraction: DealExtraction, all_results_json: str) -> str:
    return f"""Given the deal context and web search results below, summarize the findings \
into the following categories. For each category, provide a concise prose summary \
citing specific data points and sources.

Deal context:
- Company: {extraction.company_name or 'Unknown'}
- Sector: {extraction.sector or 'Unknown'}
- Sub-sector: {extraction.sub_sector or 'Unknown'}

<search_results>
{all_results_json}
</search_results>

Use the summarize_enrichment tool to return your findings."""


SUMMARIZE_TOOL = {
    "name": "summarize_enrichment",
    "description": "Summarize web search results into structured enrichment categories.",
    "input_schema": {
        "type": "object",
        "properties": {
            "comparable_multiples": {
                "type": ["string", "null"],
                "description": "Summary of comparable company trading multiples (EV/Revenue, EV/EBITDA)",
            },
            "recent_transactions": {
                "type": ["string", "null"],
                "description": "Summary of recent M&A transactions in the sector (last 24 months)",
            },
            "company_news": {
                "type": ["string", "null"],
                "description": "Recent news about the target company",
            },
            "competitive_landscape": {
                "type": ["string", "null"],
                "description": "Key competitors, market share, and competitive dynamics",
            },
            "sector_macro": {
                "type": ["string", "null"],
                "description": "Macro trends, tailwinds, headwinds, and regulatory context",
            },
            "management_backgrounds": {
                "type": ["string", "null"],
                "description": "Background information on key management team members",
            },
        },
    },
}
