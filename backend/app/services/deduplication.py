"""
Deduplication service.

Checks whether a job already exists before inserting, and merges
duplicate records when re-ingested from different sources.
"""
from __future__ import annotations

import hashlib
import re
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

logger = structlog.get_logger(__name__)


def compute_dedup_hash(company: str | None, title: str | None, url: str | None) -> str:
    """
    Canonical dedup key: lower-cased company + title + normalized URL.
    URL fragment and query params stripped. Any argument may be None.
    """
    safe_url = (url or "").lower().strip()
    clean_url = re.sub(r"[?#].*$", "", safe_url)
    clean_url = re.sub(r"/$", "", clean_url)
    key = "|".join([
        (company or "").lower().strip(),
        (title or "").lower().strip(),
        clean_url,
    ])
    return hashlib.sha256(key.encode()).hexdigest()


def compute_url_hash(url: str) -> str:
    """Dedup hash based only on URL (used before company/title are parsed)."""
    clean = re.sub(r"[?#].*$", "", url.lower().strip())
    return hashlib.sha256(clean.encode()).hexdigest()


async def find_existing_job(
    db: AsyncSession,
    user_id: uuid.UUID,
    dedup_hash: str,
) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.user_id == user_id,
            Job.dedup_hash == dedup_hash,
            Job.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def update_dedup_hash_after_parse(
    db: AsyncSession,
    job: Job,
) -> None:
    """
    Once a job is parsed, recompute the canonical dedup hash with
    company + title + url and check for any collision with an existing record.
    """
    if not (job.company and job.title):
        return

    new_hash = compute_dedup_hash(
        job.company or "",
        job.title or "",
        job.raw_url or "",
    )

    if new_hash == job.dedup_hash:
        return  # No change needed

    # Check for collision with another job
    existing = await find_existing_job(db, job.user_id, new_hash)
    if existing and existing.id != job.id:
        logger.info(
            "dedup_merge",
            keeping=str(existing.id),
            removing=str(job.id),
        )
        # Soft-delete the duplicate
        from datetime import datetime, timezone
        job.deleted_at = datetime.now(timezone.utc)
        job.status = "rejected_by_user"
    else:
        job.dedup_hash = new_hash
