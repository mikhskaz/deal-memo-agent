"""POST /upload — accepts PDF, returns job_id."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, File, UploadFile, HTTPException

from models.job import Job
from storage.job_store import create_job
from pipeline.orchestrator import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload")
async def upload_cim(file: UploadFile = File(...)):
    """Upload a CIM PDF and start the analysis pipeline.

    Returns a job_id to track progress via /status/{job_id}.
    """
    # Validate file type
    if not file.content_type or "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must have a .pdf extension")

    # Read file bytes
    pdf_bytes = await file.read()

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large — maximum size is {MAX_FILE_SIZE // (1024*1024)} MB",
        )

    # Validate PDF magic bytes
    if not pdf_bytes[:5] == b"%PDF-":
        raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF")

    # Create job
    job_id = str(uuid.uuid4())
    job = create_job(job_id)

    logger.info("[job:%s] Upload received: %s (%.1f MB)", job_id, file.filename, len(pdf_bytes) / 1e6)

    # Start pipeline as background task
    asyncio.create_task(run_pipeline(job, pdf_bytes))

    return {"job_id": job_id, "status": "queued"}
