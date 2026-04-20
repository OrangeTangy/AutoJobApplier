"""
Celery tasks.

All DB access uses synchronous SQLAlchemy because Celery workers are sync.
Async DB logic lives in the router background tasks; Celery handles
longer-running or scheduled operations.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog

from app.workers.celery_app import celery

logger = structlog.get_logger(__name__)


def _run(coro):
    """Run an async coroutine in a Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery.task(name="app.workers.tasks.poll_all_sources", bind=True, max_retries=3)
def poll_all_sources(self):
    """Poll all active ingestion sources for new job listings."""
    _run(_poll_all_sources_async())


async def _poll_all_sources_async() -> None:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.source import IngestionSource

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(IngestionSource).where(IngestionSource.is_active == True)
        )
        sources = result.scalars().all()

    for source in sources:
        poll_ingestion_source.delay(str(source.id))
    logger.info("poll_all_sources_scheduled", count=len(sources))


@celery.task(
    name="app.workers.tasks.poll_ingestion_source",
    bind=True,
    max_retries=3,
    queue="ingestion",
)
def poll_ingestion_source(self, source_id: str):
    """Poll a single ingestion source for new emails / listings."""
    try:
        _run(_poll_source_async(uuid.UUID(source_id)))
    except Exception as exc:
        logger.error("poll_source_failed", source_id=source_id, error=str(exc))
        raise self.retry(exc=exc, countdown=300)


async def _poll_source_async(source_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.source import IngestionSource

    async with AsyncSessionLocal() as db:
        source = await db.get(IngestionSource, source_id)
        if not source or not source.is_active:
            return

        if source.source_type == "imap":
            await _poll_imap_source(source, db)
        elif source.source_type == "gmail":
            await _poll_gmail_source(source, db)

        source.last_polled_at = datetime.now(timezone.utc)
        await db.commit()


async def _poll_imap_source(source, db) -> None:
    """Poll IMAP for job-related emails."""
    from app.utils.encryption import decrypt

    config = source.config
    password = decrypt(config.get("password", ""))
    # Placeholder: real implementation uses imapclient to fetch unseen emails
    logger.info("imap_poll_stub", source_id=str(source.id))


async def _poll_gmail_source(source, db) -> None:
    """Poll Gmail via API for job-related emails."""
    logger.info("gmail_poll_stub", source_id=str(source.id))


@celery.task(
    name="app.workers.tasks.prepare_application_draft",
    bind=True,
    max_retries=2,
    queue="generation",
)
def prepare_application_draft(self, application_id: str, user_id: str):
    """Full draft preparation: tailor resume + generate questionnaire answers."""
    try:
        _run(_prepare_draft_async(uuid.UUID(application_id), uuid.UUID(user_id)))
    except Exception as exc:
        logger.error("prepare_draft_failed", app_id=application_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)


async def _prepare_draft_async(app_id: uuid.UUID, user_id: uuid.UUID) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models.application import Application
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.user import UserProfile

    async with AsyncSessionLocal() as db:
        app = await db.execute(
            select(Application)
            .options(selectinload(Application.answers))
            .where(Application.id == app_id)
        )
        app = app.scalar_one_or_none()
        if not app:
            return

        job = await db.get(Job, app.job_id)
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()

        if profile and job:
            logger.info("draft_prep_complete", app_id=str(app_id))


@celery.task(
    name="app.workers.tasks.run_submission_task",
    bind=True,
    max_retries=0,   # No retries for submissions — human must re-approve
    queue="submission",
)
def run_submission_task(self, application_id: str):
    """
    Submit an approved application.

    max_retries=0 because any failure should surface to the user for review,
    not silently retry. A failed submission must never auto-resubmit.
    """
    _run(_run_submission_async(uuid.UUID(application_id)))


async def _run_submission_async(app_id: uuid.UUID) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models.application import Application
    from app.services.submission_runner import VerificationRequired, run_submission

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Application)
            .options(selectinload(Application.answers))
            .where(Application.id == app_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            logger.error("submission_app_not_found", app_id=str(app_id))
            return

        try:
            await run_submission(app, db)
            await db.commit()
        except VerificationRequired as exc:
            logger.warning(
                "submission_requires_human",
                app_id=str(app_id),
                challenge=exc.challenge_type,
            )
            await db.commit()
        except Exception as exc:
            logger.error("submission_task_failed", app_id=str(app_id), error=str(exc))
            await db.commit()
            raise


@celery.task(name="app.workers.tasks.cleanup_stale_drafts")
def cleanup_stale_drafts():
    """Mark drafts older than 30 days with no progress as expired."""
    _run(_cleanup_stale_drafts_async())


async def _cleanup_stale_drafts_async() -> None:
    from sqlalchemy import select, update

    from app.database import AsyncSessionLocal
    from app.models.application import Application

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Application)
            .where(
                Application.status == "draft",
                Application.created_at < cutoff,
            )
            .values(status="expired")
        )
        await db.commit()
    logger.info("stale_drafts_cleaned")
