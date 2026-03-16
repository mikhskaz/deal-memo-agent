"""In-memory job store. Swap for Redis in production."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from models.job import Job

logger = logging.getLogger(__name__)

# In-memory store: job_id -> Job
_jobs: dict[str, Job] = {}

# SSE event queues: job_id -> list of asyncio.Queue
_event_queues: dict[str, list[asyncio.Queue]] = {}


def create_job(job_id: str) -> Job:
    """Create a new job and return it."""
    job = Job(job_id=job_id, created_at=datetime.utcnow())
    _jobs[job_id] = job
    _event_queues[job_id] = []
    logger.info("[job:%s] Created", job_id)
    return job


def get_job(job_id: str) -> Job | None:
    """Get a job by ID."""
    return _jobs.get(job_id)


def update_job(job: Job) -> None:
    """Update a job in the store."""
    _jobs[job.job_id] = job


def delete_job(job_id: str) -> None:
    """Delete a job and its event queues."""
    _jobs.pop(job_id, None)
    _event_queues.pop(job_id, None)
    logger.info("[job:%s] Deleted from store", job_id)


def subscribe(job_id: str) -> asyncio.Queue:
    """Subscribe to SSE events for a job. Returns a queue to read from."""
    queue: asyncio.Queue = asyncio.Queue()
    if job_id not in _event_queues:
        _event_queues[job_id] = []
    _event_queues[job_id].append(queue)
    return queue


def unsubscribe(job_id: str, queue: asyncio.Queue) -> None:
    """Unsubscribe from SSE events for a job."""
    if job_id in _event_queues:
        try:
            _event_queues[job_id].remove(queue)
        except ValueError:
            pass


async def publish_event(job_id: str, event: dict) -> None:
    """Publish an SSE event to all subscribers of a job."""
    if job_id not in _event_queues:
        return
    for queue in _event_queues[job_id]:
        await queue.put(event)
