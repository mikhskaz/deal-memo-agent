"""Prompt templates for memo section drafting."""

from __future__ import annotations

from models.deal import DealExtraction, DealEnrichment

DRAFTING_SYSTEM = """You are a senior investment analyst at Sagard, a multi-strategy alternative \
asset management firm. You write clear, rigorous, concise investment memos.

Style:
- Institutional tone: direct, analytical, no marketing language
- Numbers always cited with source (CIM or web search result)
- Flag uncertainty explicitly: "per management", "CIM states", "based on public comps"
- Do not fabricate figures, names, or transactions
- Bullet points for risks and diligence questions; prose for summaries"""


SECTION_PROMPTS = {
    "executive_summary": """Write the Executive Summary section of an investment memo.

This should be 200-300 words covering:
- One-line deal description (company, sector, deal type)
- Key financial metrics (revenue, EBITDA, growth rate)
- Asking price / valuation and implied multiples if available
- Top 2-3 reasons this deal is attractive
- Top 2-3 key risks
- Recommended next step

Use the data from the CIM extraction and web enrichment below. Only cite facts present in the data.""",

    "business_description": """Write the Business Description section of an investment memo.

This should be 200-400 words covering:
- What the company does (products/services, business model)
- Founded year, headquarters, employee count
- Key customers and end markets
- Competitive advantages / moats
- Geographic footprint

Use the data from the CIM extraction and web enrichment below. Only cite facts present in the data.""",

    "market_opportunity": """Write the Market Opportunity section of an investment memo.

This should be 200-400 words covering:
- Total addressable market (TAM) size and growth
- Key market trends and tailwinds
- Regulatory environment
- Competitive landscape — who are the main competitors and how does the target compare?

Cite specific data from the CIM and web search results. Flag any figures from web searches as "based on public sources".""",

    "financial_overview": """Write the Financial Overview section of an investment memo.

This should be 300-500 words covering:
- Revenue (current, prior year, growth rate)
- EBITDA and EBITDA margin
- ARR, gross margin, NRR if available (SaaS metrics)
- Asking price / valuation
- Implied valuation multiples (EV/Revenue, EV/EBITDA) based on asking price
- Comparison to public comps if comparable multiples are available from enrichment
- Any other notable financial metrics

Present financial data in a structured format. Clearly distinguish CIM figures from public comp data.""",

    "key_risks": """Write the Key Risks section of an investment memo.

Present as a bulleted list of 5-8 risks. For each risk:
- State the risk clearly in one sentence
- Provide a brief explanation (1-2 sentences) of why it matters and potential impact
- Note any mitigants if apparent from the data

Include risks mentioned in the CIM as well as risks identified from web research (regulatory, competitive, macro).""",

    "management_team": """Write the Management Team section of an investment memo.

For each named management team member:
- Name and title
- Background summary (prior roles, education, years of experience)
- Relevance to the business

If web enrichment includes additional background beyond the CIM, incorporate it and note the source. \
If management information is limited, note this as a gap for diligence.""",

    "diligence_questions": """Write the Diligence Questions section of an investment memo.

Generate 8-12 focused diligence questions organized by category:
- Financial (revenue quality, customer concentration, churn, pipeline)
- Operational (scalability, key person risk, technology stack)
- Market (competitive threats, regulatory risks, TAM validation)
- Legal / Compliance (pending litigation, IP ownership, regulatory approvals)

These questions should be specific to this deal based on the extracted data, not generic boilerplate.""",

    "recommended_next_step": """Write the Recommended Next Step section of an investment memo.

This should be 100-200 words covering:
- Whether this deal warrants further diligence (and why)
- Specific next steps (management meeting, data room review, model build, etc.)
- Key items to validate before proceeding
- Any deal-specific timing considerations

Frame this as a recommendation to the investment committee.""",
}


def section_prompt(
    section: str,
    extraction: DealExtraction,
    enrichment: DealEnrichment,
) -> str:
    """Build the full user prompt for a memo section."""
    base_prompt = SECTION_PROMPTS[section]

    return f"""{base_prompt}

<cim_extraction>
{extraction.model_dump_json(indent=2)}
</cim_extraction>

<web_enrichment>
{enrichment.model_dump_json(indent=2, exclude={"sources"})}
</web_enrichment>

Write the section now in markdown format. Do not include the section title as a heading — it will be added automatically."""
