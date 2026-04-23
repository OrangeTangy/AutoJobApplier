"""Batch import router — Handshake CSV, URL list, JSON array."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import Job
from app.models.user import User
from app.routers.deps import get_current_user
from app.services.handshake_import import parse_batch_urls, parse_handshake_csv, parse_json_import
from app.utils.audit import write_audit

router = APIRouter(prefix="/import", tags=["import"])
logger = structlog.get_logger(__name__)


class ImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    errors: int


@router.post("/handshake", response_model=ImportResult)
async def import_handshake_csv(
    file: UploadFile = File(..., description="Handshake CSV export"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import jobs from a Handshake CSV export."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Must be a CSV file")

    content = (await file.read()).decode("utf-8", errors="replace")
    job_dicts = parse_handshake_csv(content, current_user.id)
    return await _bulk_insert_jobs(job_dicts, current_user.id, db, background_tasks, "handshake_csv")


@router.post("/urls", response_model=ImportResult)
async def import_url_list(
    file: UploadFile = File(None, description="Plain text file, one URL per line"),
    urls_text: str | None = Form(None, description="Newline-separated URLs"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import jobs from a plain text URL list."""
    if file:
        content = (await file.read()).decode("utf-8", errors="replace")
    elif urls_text:
        content = urls_text
    else:
        raise HTTPException(status_code=400, detail="Provide file or urls_text")

    job_dicts = parse_batch_urls(content, current_user.id)
    return await _bulk_insert_jobs(job_dicts, current_user.id, db, background_tasks, "batch_urls")


@router.post("/json", response_model=ImportResult)
async def import_json(
    file: UploadFile = File(..., description="JSON array of job objects"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import jobs from a JSON array."""
    content = (await file.read()).decode("utf-8", errors="replace")
    try:
        job_dicts = parse_json_import(content, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await _bulk_insert_jobs(job_dicts, current_user.id, db, background_tasks, "json_import")


async def _bulk_insert_jobs(
    job_dicts: list[dict],
    user_id: uuid.UUID,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    source: str,
) -> ImportResult:
    imported = skipped = errors = 0
    parse_queue: list[tuple[uuid.UUID, str]] = []

    for jd in job_dicts:
        try:
            # Check for duplicate
            from sqlalchemy import select
            existing = await db.execute(
                select(Job).where(
                    Job.user_id == user_id,
                    Job.dedup_hash == jd["dedup_hash"],
                    Job.deleted_at.is_(None),
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            job = Job(
                user_id=user_id,
                dedup_hash=jd["dedup_hash"],
                raw_url=jd.get("raw_url"),
                title=jd.get("title"),
                company=jd.get("company"),
                location=jd.get("location"),
                description=jd.get("description"),
                status=jd.get("status", "new"),
                discovered_at=jd.get("discovered_at", datetime.now(timezone.utc)),
            )
            db.add(job)
            await db.flush()
            imported += 1

            # Queue URL-based jobs for LLM parsing
            if job.raw_url and job.status == "new":
                parse_queue.append((job.id, job.raw_url))

        except Exception as exc:
            logger.error("bulk_insert_error", error=str(exc))
            errors += 1

    await write_audit(
        db,
        action="bulk_import",
        actor="user",
        user_id=user_id,
        metadata={"source": source, "imported": imported, "skipped": skipped},
    )

    # Schedule parsing for new URL-based jobs
    from app.routers.jobs import _parse_and_score_job
    for job_id, url in parse_queue:
        background_tasks.add_task(_parse_and_score_job, job_id, url, str(user_id))

    return ImportResult(imported=imported, skipped_duplicates=skipped, errors=errors)
