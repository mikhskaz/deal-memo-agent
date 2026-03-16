"""GET /memo/{job_id} — returns final memo JSON + markdown.
GET /download/{job_id}.docx — returns the DOCX file."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from storage.job_store import get_job

logger = logging.getLogger(__name__)

router = APIRouter()


def _job_dir(job_id: str) -> Path:
    return Path(tempfile.gettempdir()) / "deal-memo-agent" / job_id


@router.get("/memo/{job_id}")
async def get_memo(job_id: str):
    """Return the completed memo with extraction data and sources."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed at stage '{job.current_stage}': {job.error}",
        )

    if job.status != "complete":
        raise HTTPException(
            status_code=202,
            detail=f"Pipeline still running — current stage: {job.current_stage}",
        )

    if not job.memo:
        raise HTTPException(status_code=500, detail="Memo data is missing")

    # Build response
    memo_sections = {}
    for section_id, section in job.memo.sections.items():
        memo_sections[section_id] = section.content

    sources = []
    if job.enrichment:
        sources = [
            {"query": s.query, "url": s.url, "title": s.title}
            for s in job.enrichment.sources
        ]

    company_name = job.extraction.company_name if job.extraction else None

    return {
        "job_id": job_id,
        "company_name": company_name,
        "generated_at": job.memo.generated_at.isoformat(),
        "memo": memo_sections,
        "extraction": job.extraction.model_dump() if job.extraction else None,
        "sources": sources,
        "docx_download_url": f"/download/{job_id}.docx",
    }


@router.get("/download/{job_id}.docx")
async def download_docx(job_id: str):
    """Download the generated DOCX memo."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "complete":
        raise HTTPException(status_code=400, detail="Memo not ready yet")

    docx_path = _job_dir(job_id) / "memo.docx"
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="DOCX file not found")

    company = job.extraction.company_name if job.extraction and job.extraction.company_name else "deal"
    filename = f"{company.replace(' ', '_')}_memo.docx"

    return FileResponse(
        path=str(docx_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
