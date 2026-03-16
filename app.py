"""FastAPI entrypoint for the Deal Memo Agent."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import settings
from api.middleware import setup_middleware
from api.routes.upload import router as upload_router
from api.routes.status import router as status_router
from api.routes.memo import router as memo_router
from storage.job_store import get_job, delete_job

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(levelname)-5s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def cleanup_old_jobs():
    """Background task: delete temp files for jobs completed more than 1 hour ago."""
    base_dir = Path(tempfile.gettempdir()) / "deal-memo-agent"
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        if not base_dir.exists():
            continue
        now = datetime.utcnow()
        for job_dir in base_dir.iterdir():
            if not job_dir.is_dir():
                continue
            job_id = job_dir.name
            job = get_job(job_id)
            if job and job.completed_at:
                elapsed = (now - job.completed_at).total_seconds()
                if elapsed > 3600:  # 1 hour
                    shutil.rmtree(str(job_dir), ignore_errors=True)
                    delete_job(job_id)
                    logger.info("[job:%s] Cleaned up (%.0f min old)", job_id, elapsed / 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start background tasks."""
    cleanup_task = asyncio.create_task(cleanup_old_jobs())
    logger.info("Deal Memo Agent started on port %d", settings.PORT)
    yield
    cleanup_task.cancel()


app = FastAPI(
    title="Deal Memo Agent",
    description="AI-powered investment memo drafting system",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware
setup_middleware(app)

# API routes
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(memo_router)

# Serve frontend static files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=settings.PORT, reload=True)
