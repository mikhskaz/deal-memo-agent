"""Pipeline orchestrator — runs all stages in order, manages state and SSE events."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from models.job import Job
from storage.job_store import update_job, publish_event
from pipeline.ingest import ingest
from pipeline.extract import extract
from pipeline.enrich import enrich
from pipeline.draft import draft
from pipeline.export import export

logger = logging.getLogger(__name__)

STAGES = ["ingest", "extract", "enrich", "draft", "export"]


def _job_dir(job_id: str) -> Path:
    """Get the temp directory for a job."""
    return Path(tempfile.gettempdir()) / "deal-memo-agent" / job_id


async def _emit(job_id: str, stage: str, status: str, progress: float, message: str = ""):
    """Publish a pipeline update event."""
    event = {
        "event": "pipeline_update",
        "stage": stage,
        "status": status,
        "progress": progress,
        "message": message,
    }
    await publish_event(job_id, event)


async def run_pipeline(job: Job, pdf_bytes: bytes) -> None:
    """Run the full pipeline for a job.

    Stages: ingest → extract → enrich → draft → export

    Updates the job state and publishes SSE events at each stage.
    """
    job_id = job.job_id
    job.status = "running"
    update_job(job)

    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded PDF
    (job_dir / "input.pdf").write_bytes(pdf_bytes)

    total_tokens = 0

    try:
        # --- Stage 1: Ingest ---
        job.current_stage = "ingest"
        update_job(job)
        await _emit(job_id, "ingest", "running", 0.0, "Parsing PDF...")

        chunks = await ingest(pdf_bytes)

        await _emit(
            job_id, "ingest", "complete", 1.0,
            f"Parsed {len(chunks)} chunks",
        )
        logger.info("[job:%s] Stage ingest complete — %d chunks", job_id, len(chunks))

        # --- Stage 2: Extract ---
        job.current_stage = "extract"
        update_job(job)
        await _emit(
            job_id, "extract", "running", 0.0,
            f"Extracting fields from {len(chunks)} chunks...",
        )

        extraction, extract_tokens = await extract(chunks)
        total_tokens += extract_tokens

        job.extraction = extraction
        update_job(job)

        # Save extraction
        (job_dir / "extracted.json").write_text(
            extraction.model_dump_json(indent=2), encoding="utf-8"
        )

        await _emit(job_id, "extract", "complete", 1.0, "Extraction complete")
        logger.info("[job:%s] Stage extract complete — tokens used: %d", job_id, extract_tokens)

        # --- Stage 3: Enrich ---
        job.current_stage = "enrich"
        update_job(job)
        await _emit(
            job_id, "enrich", "running", 0.0,
            "Generating search queries and researching...",
        )

        enrichment, enrich_tokens = await enrich(extraction)
        total_tokens += enrich_tokens

        job.enrichment = enrichment
        update_job(job)

        # Save enrichment
        (job_dir / "enriched.json").write_text(
            enrichment.model_dump_json(indent=2), encoding="utf-8"
        )

        await _emit(
            job_id, "enrich", "complete", 1.0,
            f"Enrichment complete — {len(enrichment.sources)} sources found",
        )
        logger.info(
            "[job:%s] Stage enrich complete — %d sources",
            job_id, len(enrichment.sources),
        )

        # --- Stage 4: Draft ---
        job.current_stage = "draft"
        update_job(job)
        await _emit(job_id, "draft", "running", 0.0, "Drafting memo sections...")

        memo, draft_tokens = await draft(extraction, enrichment)
        total_tokens += draft_tokens
        memo.total_tokens_used = total_tokens

        job.memo = memo
        update_job(job)

        # Save memo
        (job_dir / "memo.json").write_text(
            memo.model_dump_json(indent=2), encoding="utf-8"
        )

        await _emit(job_id, "draft", "complete", 1.0, "All sections drafted")
        logger.info("[job:%s] Stage draft complete", job_id)

        # --- Stage 5: Export ---
        job.current_stage = "export"
        update_job(job)
        await _emit(job_id, "export", "running", 0.0, "Rendering memo...")

        markdown, docx_path = await export(memo, extraction, enrichment, job_dir)

        await _emit(job_id, "export", "complete", 1.0, "Export complete")
        logger.info("[job:%s] Stage export complete", job_id)

        # --- Done ---
        job.status = "complete"
        job.completed_at = datetime.utcnow()
        update_job(job)

        await publish_event(job_id, {
            "event": "complete",
            "job_id": job_id,
            "memo_ready": True,
        })

        elapsed = (job.completed_at - job.created_at).total_seconds()
        logger.info(
            "[job:%s] Pipeline complete — total tokens: %d, elapsed: %.0fs",
            job_id, total_tokens, elapsed,
        )

    except Exception as e:
        logger.error("[job:%s] Pipeline failed at stage %s: %s", job_id, job.current_stage, e)
        job.status = "failed"
        job.error = str(e)
        update_job(job)

        await publish_event(job_id, {
            "event": "error",
            "stage": job.current_stage,
            "message": str(e),
        })
