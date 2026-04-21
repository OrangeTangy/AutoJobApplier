from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import Job
from app.models.user import User, UserProfile
from app.routers.deps import get_current_user
from app.schemas.job import JobFilters, JobIngest, JobListOut, JobOut
from app.services.job_parser import compute_dedup_hash, parse_job_from_url
from app.utils.audit import write_audit

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = structlog.get_logger(__name__)


@router.post("/ingest", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def ingest_job_url(
    body: JobIngest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    """Ingest a job posting URL. Parses and scores in background."""
    # Create stub job record immediately
    now = datetime.now(timezone.utc)

    # Dedup hash using URL alone initially (company/title parsed async)
    dedup_hash = hashlib.sha256(body.url.lower().strip().encode()).hexdigest()

    # Check for duplicate
    existing = await db.execute(
        select(Job).where(Job.user_id == current_user.id, Job.dedup_hash == dedup_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This job URL has already been ingested")

    job = Job(
        user_id=current_user.id,
        dedup_hash=dedup_hash,
        raw_url=body.url,
        status="parsing",
        discovered_at=now,
    )
    db.add(job)
    await db.flush()
    job_id = job.id

    await write_audit(
        db,
        action="job_discovered",
        actor="user",
        user_id=current_user.id,
        resource_type="job",
        resource_id=job_id,
        metadata={"url": body.url},
    )

    # Schedule async parse
    background_tasks.add_task(_parse_and_score_job, job_id, body.url, str(current_user.id))

    return job


async def _parse_and_score_job(job_id: uuid.UUID, url: str, user_id: str) -> None:
    """Background task: parse job URL and score fit against user profile."""
    from app.database import AsyncSessionLocal
    from app.services.fit_scorer import score_job_fit

    async with AsyncSessionLocal() as db:
        try:
            job = await db.get(Job, job_id)
            if not job:
                return

            # Fetch and parse
            raw_html, _text, parsed = await parse_job_from_url(url)

            # Update dedup hash with proper company+title
            job.dedup_hash = compute_dedup_hash(
                parsed.company or "", parsed.title or "", url
            )
            job.raw_html = raw_html[:50000]  # cap storage
            job.title = parsed.title
            job.company = parsed.company
            job.location = parsed.location
            job.remote_policy = parsed.remote_policy
            job.description = parsed.description
            job.required_skills = parsed.required_skills
            job.preferred_skills = parsed.preferred_skills
            job.years_experience_min = parsed.years_experience_min
            job.years_experience_max = parsed.years_experience_max
            job.sponsorship_hint = parsed.sponsorship_hint
            job.salary_min = parsed.salary_min
            job.salary_max = parsed.salary_max
            job.salary_currency = parsed.salary_currency
            job.application_url = parsed.application_url
            job.application_questions = [q.model_dump() for q in parsed.application_questions]
            job.parse_rationale = {"summary": parsed.parse_rationale}
            job.status = "parsed"

            # Score fit
            profile_result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == job.user_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile:
                fit = score_job_fit(
                    job_data={
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "remote_policy": job.remote_policy,
                        "description": job.description,
                        "required_skills": job.required_skills,
                        "preferred_skills": job.preferred_skills,
                        "years_experience_min": job.years_experience_min,
                        "sponsorship_hint": job.sponsorship_hint,
                    },
                    profile_data={
                        "skills": profile.skills,
                        "work_authorization": profile.work_authorization,
                        "requires_sponsorship": profile.requires_sponsorship,
                        "willing_to_relocate": profile.willing_to_relocate,
                        "target_locations": profile.target_locations,
                        "work_history": profile.work_history,
                        "education": profile.education,
                    },
                )
                job.fit_score = fit.score
                job.fit_rationale = fit.model_dump()

            job.status = "scored"
            await db.commit()
            logger.info("job_scored_async", job_id=str(job_id), score=job.fit_score)

        except Exception as exc:
            logger.error("async_parse_failed", job_id=str(job_id), error=str(exc))
            job = await db.get(Job, job_id)
            if job:
                job.status = "error"
                job.parse_error = str(exc)[:500]
                await db.commit()


@router.get("", response_model=JobListOut)
async def list_jobs(
    status: str | None = Query(None),
    company: str | None = Query(None),
    min_fit_score: int | None = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListOut:
    q = select(Job).where(Job.user_id == current_user.id, Job.deleted_at.is_(None))

    if status:
        q = q.where(Job.status == status)
    if company:
        q = q.where(Job.company.ilike(f"%{company}%"))
    if min_fit_score is not None:
        q = q.where(Job.fit_score >= min_fit_score)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(Job.fit_score.desc().nullslast(), Job.discovered_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    jobs = (await db.execute(q)).scalars().all()

    return JobListOut(items=list(jobs), total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    job = await _get_job_or_404(job_id, current_user.id, db)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    job = await _get_job_or_404(job_id, current_user.id, db)
    job.deleted_at = datetime.now(timezone.utc)
    job.status = "rejected_by_user"


async def _get_job_or_404(
    job_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user_id, Job.deleted_at.is_(None))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
