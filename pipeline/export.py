"""Stage 5: Export — Render memo to markdown and DOCX."""

from __future__ import annotations

import logging
from pathlib import Path

from models.deal import DealExtraction, DealEnrichment, Memo, SearchResult
from utils.docx_renderer import render_docx, SECTION_TITLES, SECTION_ORDER

logger = logging.getLogger(__name__)


def render_markdown(
    memo: Memo,
    extraction: DealExtraction,
    sources: list[SearchResult],
) -> str:
    """Render the memo as a markdown string."""
    parts: list[str] = []

    # Header
    company_name = extraction.company_name or "Deal"
    parts.append(f"# Investment Memo: {company_name}")
    parts.append("")
    parts.append(f"*Generated: {memo.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*")
    parts.append(f"*Model: {memo.model_used}*")
    parts.append("")
    parts.append("> **AI-ASSISTED DRAFT — FOR INTERNAL REVIEW ONLY — NOT FOR DISTRIBUTION**")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Sections
    for section_id in SECTION_ORDER:
        section = memo.sections.get(section_id)
        if not section:
            continue

        title = SECTION_TITLES.get(section_id, section_id.replace("_", " ").title())
        parts.append(f"## {title}")
        parts.append("")
        parts.append(section.content)
        parts.append("")
        parts.append("---")
        parts.append("")

    # Sources appendix
    if sources:
        parts.append("## Sources")
        parts.append("")
        for i, source in enumerate(sources, 1):
            parts.append(f"{i}. **{source.title}**")
            parts.append(f"   - URL: {source.url}")
            parts.append(f"   - Query: {source.query}")
            parts.append("")

    return "\n".join(parts)


async def export(
    memo: Memo,
    extraction: DealExtraction,
    enrichment: DealEnrichment,
    output_dir: str | Path,
) -> tuple[str, Path]:
    """Export memo to markdown and DOCX.

    Returns:
        Tuple of (markdown_string, docx_path)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = enrichment.sources

    # Render markdown
    markdown = render_markdown(memo, extraction, sources)
    md_path = output_dir / "memo.md"
    md_path.write_text(markdown, encoding="utf-8")
    logger.info("Markdown memo saved to %s", md_path)

    # Render DOCX
    docx_path = output_dir / "memo.docx"
    render_docx(memo, extraction, sources, docx_path)

    return markdown, docx_path
