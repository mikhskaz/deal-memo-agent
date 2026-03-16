"""GET /status/{job_id} — SSE stream of pipeline progress."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from storage.job_store import get_job, subscribe, unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status/{job_id}")
async def stream_status(job_id: str):
    """Stream pipeline progress via Server-Sent Events.

    Events:
        pipeline_update: stage progress updates
        complete: pipeline finished successfully
        error: pipeline encountered an error
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job is already complete or failed, return final status immediately
    if job.status in ("complete", "failed"):
        async def finished_stream():
            if job.status == "complete":
                yield {
                    "event": "complete",
                    "data": json.dumps({"job_id": job_id, "memo_ready": True}),
                }
            else:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "stage": job.current_stage,
                        "message": job.error or "Unknown error",
                    }),
                }

        return EventSourceResponse(finished_stream())

    # Subscribe to live events
    queue = subscribe(job_id)

    async def event_stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "keepalive", "data": "{}"}
                    continue

                event_type = event.get("event", "pipeline_update")
                yield {
                    "event": event_type,
                    "data": json.dumps(event),
                }

                # Stop streaming after completion or error
                if event_type in ("complete", "error"):
                    break
        finally:
            unsubscribe(job_id, queue)

    return EventSourceResponse(event_stream())
