"""Prompt templates for CIM field extraction."""

from __future__ import annotations

from utils.chunker import Chunk

EXTRACTION_SYSTEM = """You are a senior investment analyst assistant. You will be given a section of a \
Confidential Information Memorandum (CIM). Extract all available information \
into the JSON schema provided via the tool.

Rules:
- Only extract information explicitly stated in the text.
- If a field is not present in this section, return null — do not infer or estimate.
- For financial figures, always include the unit (e.g. "$12.4M", "£3.2B").
- For dates, use ISO 8601 format (YYYY or YYYY-MM).
- Be exhaustive — capture every number, name, and metric you find."""


def extraction_user_prompt(chunk: Chunk) -> str:
    return f"""Extract deal information from the following section of a CIM.
This is chunk {chunk.index} covering pages {chunk.page_range[0]}–{chunk.page_range[1]}.

<document_section>
{chunk.text}
</document_section>

Use the extract_deal_data tool to return your findings."""


EXTRACTION_TOOL = {
    "name": "extract_deal_data",
    "description": "Extract structured deal information from a CIM section.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": ["string", "null"]},
            "company_description": {"type": ["string", "null"]},
            "founded_year": {"type": ["integer", "null"]},
            "headquarters": {"type": ["string", "null"]},
            "sector": {"type": ["string", "null"]},
            "sub_sector": {"type": ["string", "null"]},
            "business_model": {"type": ["string", "null"]},
            "revenue_current": {"type": ["string", "null"]},
            "revenue_prior_year": {"type": ["string", "null"]},
            "revenue_growth_rate": {"type": ["string", "null"]},
            "ebitda_current": {"type": ["string", "null"]},
            "ebitda_margin": {"type": ["string", "null"]},
            "arr": {"type": ["string", "null"]},
            "gross_margin": {"type": ["string", "null"]},
            "customer_count": {"type": ["integer", "null"]},
            "nrr": {"type": ["string", "null"]},
            "asking_price_or_valuation": {"type": ["string", "null"]},
            "deal_type": {
                "type": ["string", "null"],
                "enum": [
                    "buyout", "growth_equity", "venture",
                    "credit", "real_estate", None,
                ],
            },
            "management_team": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "background": {"type": ["string", "null"]},
                    },
                },
            },
            "key_customers": {"type": "array", "items": {"type": "string"}},
            "key_risks_mentioned": {"type": "array", "items": {"type": "string"}},
            "competitive_advantages": {"type": "array", "items": {"type": "string"}},
            "total_addressable_market": {"type": ["string", "null"]},
            "geographic_markets": {"type": "array", "items": {"type": "string"}},
            "employee_count": {"type": ["integer", "null"]},
            "other_notable_facts": {"type": "array", "items": {"type": "string"}},
        },
    },
}


MERGE_SYSTEM = """You are a senior investment analyst assistant. You will be given multiple \
partial extraction results from different sections of a CIM. Merge them into a \
single comprehensive extraction.

Rules:
- Combine all non-null values. If the same field appears in multiple chunks, \
use the most specific or most recent value.
- Merge all list fields (management_team, key_customers, etc.) by combining \
and deduplicating.
- Do not invent or infer values — only use what is provided in the partial extractions.
- The result should be a single, unified deal extraction."""


def merge_user_prompt(partials_json: str) -> str:
    return f"""Merge the following partial extraction results from different sections \
of the same CIM into one unified extraction.

<partial_extractions>
{partials_json}
</partial_extractions>

Use the extract_deal_data tool to return the merged result."""
