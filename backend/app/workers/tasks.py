"""
Celery tasks.

All DB access uses synchronous SQLAlchemy because Celery workers are sync.
Async DB logic lives in the router background tasks; Celery handles
longer-running or scheduled operations.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog

from app.workers.celery_app import celery, run_coro_blocking

logger = structlog.get_logger(__name__)


def _run(coro):
    """Run an async coroutine from inside a worker thread."""
    return run_coro_blocking(coro)


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
    """Poll IMAP for job-related emails and ingest new jobs."""
    from app.services.email_ingestion import poll_imap
    from app.utils.encryption import decrypt

    config = source.config or {}
    host = config.get("host", "")
    username = config.get("username", "")
    password = decrypt(config.get("password", "")) if config.get("password") else ""
    port = int(config.get("port", 993))
    use_ssl = config.get("ssl", True)

    if not host or not username or not password:
        logger.warning("imap_source_missing_config", source_id=str(source.id))
        return

    job_dicts = await poll_imap(
        source_id=source.id,
        user_id=source.user_id,
        host=host,
        port=port,
        username=username,
        password=password,
    )

    imported = 0
    for jd in job_dicts:
        from sqlalchemy import select
        from app.models.job import Job

        existing = await db.execute(
            select(Job).where(
                Job.user_id == source.user_id,
                Job.dedup_hash == jd["dedup_hash"],
                Job.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            continue

        from datetime import datetime, timezone
        job = Job(
            user_id=source.user_id,
            dedup_hash=jd["dedup_hash"],
            raw_url=jd.get("raw_url"),
            title=jd.get("title"),
            company=jd.get("company"),
            description=jd.get("description"),
            status="new",
            discovered_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()
        imported += 1

    if imported:
        await db.flush()
    logger.info("imap_poll_complete", source_id=str(source.id), imported=imported)


async def _poll_gmail_source(source, db) -> None:
    """Poll Gmail via Google API for job-related emails and ingest new jobs."""
    from app.services.email_ingestion import poll_gmail
    from app.utils.encryption import decrypt

    config = source.config or {}
    raw_token = config.get("oauth_token", "")
    oauth_token = decrypt(raw_token) if raw_token else ""

    if not oauth_token:
        logger.warning("gmail_source_missing_token", source_id=str(source.id))
        return

    job_dicts = await poll_gmail(
        source_id=source.id,
        user_id=source.user_id,
        oauth_token=oauth_token,
    )

    imported = 0
    for jd in job_dicts:
        from sqlalchemy import select
        from app.models.job import Job

        existing = await db.execute(
            select(Job).where(
                Job.user_id == source.user_id,
                Job.dedup_hash == jd["dedup_hash"],
                Job.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            continue

        from datetime import datetime, timezone
        job = Job(
            user_id=source.user_id,
            dedup_hash=jd["dedup_hash"],
            raw_url=jd.get("raw_url"),
            title=jd.get("title"),
            company=jd.get("company"),
            description=jd.get("description"),
            status="new",
            discovered_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()
        imported += 1

    logger.info("gmail_poll_complete", source_id=str(source.id), imported=imported)


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
    """
    Prepare a draft application without any LLM:
    1. Find the best-matching resume from the user's library (TF-IDF)
    2. Generate questionnaire answers directly from profile fields
    3. Advance status to ready_for_review
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from app.models.application import Application, QuestionnaireAnswer
    from app.models.job import Job
    from app.models.user import UserProfile
    from app.services.questionnaire import generate_answers
    from app.services.resume_matcher import get_best_resume

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Application)
            .options(selectinload(Application.answers))
            .where(Application.id == app_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            logger.warning("draft_app_not_found", app_id=str(app_id))
            return

        job = await db.get(Job, app.job_id)
        profile_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()

        if not job or not profile:
            logger.warning("draft_missing_job_or_profile", app_id=str(app_id))
            return

        # 1. Auto-select best matching resume from library
        job_text = f"{job.title or ''} {job.company or ''} {job.description or ''} " \
                   f"{' '.join(job.required_skills or [])} {' '.join(job.preferred_skills or [])}"

        best_resume, match_score, matched_terms = await get_best_resume(db, user_id, job_text)
        if best_resume:
            app.resume_id = best_resume.id
            logger.info(
                "resume_auto_selected",
                app_id=str(app_id),
                resume=best_resume.name,
                match_score=match_score,
                matched_terms=matched_terms[:5],
            )
        else:
            logger.warning("no_library_resume_found", app_id=str(app_id))

        # 2. Generate questionnaire answers from profile (no LLM)
        questions = job.application_questions or []
        if questions:
            profile_data = {
                "full_name": profile.full_name,
                "work_authorization": profile.work_authorization,
                "requires_sponsorship": profile.requires_sponsorship,
                "willing_to_relocate": profile.willing_to_relocate,
                "target_locations": profile.target_locations or [],
                "skills": profile.skills or [],
                "work_history": profile.work_history or [],
                "education": profile.education or [],
                "desired_salary": profile.desired_salary_min,
                "desired_salary_min": profile.desired_salary_min,
                "desired_salary_max": profile.desired_salary_max,
                "salary_currency": "USD",
                "earliest_start_date": getattr(profile, "earliest_start_date", ""),
                "location": profile.location,
            }
            answers = generate_answers(questions, profile_data)
            for ans in answers:
                qa = QuestionnaireAnswer(
                    application_id=app_id,
                    user_id=user_id,
                    question_text=ans.question_text,
                    question_type=ans.question_type,
                    draft_answer=ans.draft_answer,
                    confidence=ans.confidence,
                    sources=ans.sources,
                    rationale=ans.rationale,
                    requires_review=ans.requires_review,
                )
                db.add(qa)

        app.status = "ready_for_review"
        await db.commit()
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
