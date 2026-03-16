from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.deal import DealExtraction, DealEnrichment, Memo


class Job(BaseModel):
    job_id: str
    status: Literal["queued", "running", "complete", "failed"] = "queued"
    current_stage: str | None = None
    extraction: DealExtraction | None = None
    enrichment: DealEnrichment | None = None
    memo: Memo | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
