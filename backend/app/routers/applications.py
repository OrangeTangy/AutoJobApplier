from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.application import Application, QuestionnaireAnswer
from app.models.job import Job
from app.models.user import User, UserProfile
from app.routers.deps import get_current_user
from app.schemas.application import (
    AnswerEditRequest,
    AnswerOut,
    ApplicationApproveRequest,
    ApplicationOut,
    ApplicationRejectRequest,
    OutcomeUpdateRequest,
)
from app.utils.audit import write_audit
from app.utils.encryption import decrypt, encrypt
from app.utils.security import compute_approval_hash

router = APIRouter(prefix="/applications", tags=["applications"])
logger = structlog.get_logger(__name__)


@router.post("/{job_id}/draft", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_draft(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Application:
    """Create a draft application for a job and trigger questionnaire generation."""
    # Verify job belongs to user
    job = await _get_job_or_404(job_id, current_user.id, db)

    # Check for existing application
    existing = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.job_id == job_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Draft already exists for this job")

    app = Application(user_id=current_user.id, job_id=job_id, status="draft")
    db.add(app)
    await db.flush()

    await write_audit(
        db,
        action="application_draft_created",
        actor="user",
        user_id=current_user.id,
        resource_type="application",
        resource_id=app.id,
    )

    # Generate questionnaire answers in background
    if job.application_questions:
        background_tasks.add_task(
            _generate_questionnaire_async,
            app.id,
            job.application_questions,
            str(current_user.id),
        )

    return app


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Application]:
    q = (
        select(Application)
        .options(selectinload(Application.answers))
        .where(Application.user_id == current_user.id)
        .order_by(Application.created_at.desc())
    )
    if status_filter:
        q = q.where(Application.status == status_filter)
    result = await db.execute(q)
    apps = list(result.scalars().all())

    # Decrypt answer text for response
    for app in apps:
        for answer in app.answers:
            answer.draft_answer = decrypt(answer.draft_answer)
            if answer.final_answer:
                answer.final_answer = decrypt(answer.final_answer)
    return apps


@router.get("/{app_id}", response_model=ApplicationOut)
async def get_application(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Application:
    app = await _get_app_or_404(app_id, current_user.id, db, load_answers=True)
    for answer in app.answers:
        answer.draft_answer = decrypt(answer.draft_answer)
        if answer.final_answer:
            answer.final_answer = decrypt(answer.final_answer)
    return app


@router.patch("/{app_id}/answers/{answer_id}", response_model=AnswerOut)
async def edit_answer(
    app_id: uuid.UUID,
    answer_id: uuid.UUID,
    body: AnswerEditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireAnswer:
    app = await _get_app_or_404(app_id, current_user.id, db)
    if app.status == "submitted":
        raise HTTPException(status_code=409, detail="Cannot edit submitted application")

    result = await db.execute(
        select(QuestionnaireAnswer).where(
            QuestionnaireAnswer.id == answer_id,
            QuestionnaireAnswer.application_id == app_id,
        )
    )
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    answer.final_answer = encrypt(body.final_answer)
    answer.user_edited = True

    await write_audit(
        db,
        action="answer_edited",
        actor="user",
        user_id=current_user.id,
        resource_type="application",
        resource_id=app_id,
    )
    answer.draft_answer = decrypt(answer.draft_answer)
    answer.final_answer = body.final_answer
    return answer


@router.post("/{app_id}/approve", response_model=ApplicationOut)
async def approve_application(
    app_id: uuid.UUID,
    body: ApplicationApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Application:
    """Explicit approval gate — required before submission."""
    app = await _get_app_or_404(app_id, current_user.id, db, load_answers=True)

    if app.status not in ("draft", "ready_for_review"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve application in status '{app.status}'",
        )

    # Compute approval hash over all final answers
    final_answers = [
        decrypt(a.final_answer or a.draft_answer) for a in app.answers
    ]
    resume_id_str = str(app.resume_id) if app.resume_id else ""
    app.approval_hash = compute_approval_hash(resume_id_str, final_answers)
    app.approved_at = datetime.now(timezone.utc)
    app.approved_by = current_user.id
    app.status = "approved"
    if body.notes:
        app.user_notes = body.notes

    await write_audit(
        db,
        action="application_approved",
        actor="user",
        user_id=current_user.id,
        resource_type="application",
        resource_id=app_id,
        metadata={"approval_hash": app.approval_hash},
    )
    logger.info("application_approved", app_id=str(app_id), user=str(current_user.id))

    return app


@router.post("/{app_id}/reject", response_model=ApplicationOut)
async def reject_application(
    app_id: uuid.UUID,
    body: ApplicationRejectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Application:
    app = await _get_app_or_404(app_id, current_user.id, db)
    if app.status == "submitted":
        raise HTTPException(status_code=409, detail="Cannot reject submitted application")

    app.status = "rejected"
    if body.reason:
        app.user_notes = body.reason

    await write_audit(
        db,
        action="application_rejected_by_user",
        actor="user",
        user_id=current_user.id,
        resource_type="application",
        resource_id=app_id,
    )
    return app


@router.post("/{app_id}/submit", response_model=ApplicationOut)
async def submit_application(
    app_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Application:
    """Trigger submission for an approved application."""
    app = await _get_app_or_404(app_id, current_user.id, db, load_answers=True)

    if app.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Application must be approved before submission",
        )

    background_tasks.add_task(_submit_async, app_id, str(current_user.id))
    return app


@router.patch("/{app_id}/outcome", response_model=ApplicationOut)
async def update_outcome(
    app_id: uuid.UUID,
    body: OutcomeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Application:
    app = await _get_app_or_404(app_id, current_user.id, db)
    app.outcome = body.outcome
    if body.notes:
        app.user_notes = body.notes
    return app


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_app_or_404(
    app_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    load_answers: bool = False,
) -> Application:
    q = select(Application).where(
        Application.id == app_id, Application.user_id == user_id
    )
    if load_answers:
        q = q.options(selectinload(Application.answers))
    result = await db.execute(q)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


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


async def _generate_questionnaire_async(
    app_id: uuid.UUID,
    questions: list,
    user_id: str,
) -> None:
    from app.database import AsyncSessionLocal
    from app.services.questionnaire import generate_answers
    from app.utils.encryption import encrypt

    async with AsyncSessionLocal() as db:
        try:
            app = await db.get(Application, app_id)
            if not app:
                return

            profile_result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == app.user_id)
            )
            profile = profile_result.scalar_one_or_none()
            profile_data = profile.__dict__ if profile else {}

            answers = await generate_answers(questions, profile_data)

            for draft in answers:
                qa = QuestionnaireAnswer(
                    application_id=app_id,
                    user_id=app.user_id,
                    question_text=draft.question_text,
                    question_type=draft.question_type,
                    draft_answer=encrypt(draft.draft_answer),
                    confidence=draft.confidence,
                    requires_review=draft.requires_review,
                    sources=draft.sources,
                    rationale=draft.rationale,
                )
                db.add(qa)

            app.status = "ready_for_review"
            await db.commit()
            logger.info("questionnaire_generated", app_id=str(app_id), count=len(answers))

        except Exception as exc:
            logger.error("questionnaire_failed", app_id=str(app_id), error=str(exc))


async def _submit_async(app_id: uuid.UUID, user_id: str) -> None:
    from app.database import AsyncSessionLocal
    from app.services.submission_runner import VerificationRequired, run_submission

    async with AsyncSessionLocal() as db:
        try:
            app = await db.execute(
                select(Application)
                .options(selectinload(Application.answers))
                .where(Application.id == app_id)
            )
            app = app.scalar_one_or_none()
            if not app:
                return
            await run_submission(app, db)
            await db.commit()
        except VerificationRequired as exc:
            logger.warning("submission_challenge", app_id=str(app_id), challenge=exc.challenge_type)
            await db.commit()
        except Exception as exc:
            logger.error("submission_error", app_id=str(app_id), error=str(exc))
            await db.commit()
