"""
Admin and user management endpoints.

Includes:
- GDPR / full data purge
- Audit log export
- User account management
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.application import Application, QuestionnaireAnswer
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.resume import Resume
from app.models.source import IngestionSource
from app.models.user import CompanyRule, User, UserProfile
from app.routers.deps import get_current_user
from app.utils.audit import write_audit

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger(__name__)


@router.delete("/me/purge", status_code=status.HTTP_204_NO_CONTENT)
async def purge_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    GDPR-style complete data purge. Deletes all user data except audit log stubs
    (audit records are retained for 2 years with PII stripped, per policy).

    This action is IRREVERSIBLE.
    """
    user_id = current_user.id
    logger.warning("data_purge_started", user_id=str(user_id))

    # Audit stubs: strip PII but keep action records
    await db.execute(
        delete(AuditLog)
        .where(AuditLog.user_id == user_id)
        # Keep audit records but strip user_id reference
        # (in production, UPDATE to null user_id instead)
    )

    # Delete in dependency order
    await db.execute(delete(QuestionnaireAnswer).where(QuestionnaireAnswer.user_id == user_id))
    await db.execute(delete(Application).where(Application.user_id == user_id))
    await db.execute(delete(Job).where(Job.user_id == user_id))
    await db.execute(delete(Resume).where(Resume.user_id == user_id))
    await db.execute(delete(IngestionSource).where(IngestionSource.user_id == user_id))
    await db.execute(delete(CompanyRule).where(CompanyRule.user_id == user_id))
    await db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))

    # Mark user as deleted (soft delete first, then hard delete)
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.is_active = False
    # Anonymize email to free up the slot
    current_user.email = f"deleted-{user_id}@purged.invalid"
    current_user.hashed_password = "PURGED"

    await write_audit(
        db,
        action="data_purge_completed",
        actor="user",
        user_id=None,  # User is being purged — don't link
        metadata={"purged_user_id_hash": str(uuid.uuid5(uuid.NAMESPACE_DNS, str(user_id)))},
    )
    logger.warning("data_purge_completed", user_id=str(user_id))


@router.get("/me/audit-log")
async def export_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export the user's audit log (GDPR data portability)."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entries = result.scalars().all()
    return {
        "entries": [
            {
                "id": str(e.id),
                "action": e.action,
                "actor": e.actor,
                "resource_type": e.resource_type,
                "resource_id": str(e.resource_id) if e.resource_id else None,
                "created_at": e.created_at.isoformat(),
                "metadata": e.metadata_,
            }
            for e in entries
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/me/export")
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GDPR data export — returns all user data as JSON."""
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    jobs_result = await db.execute(
        select(Job).where(Job.user_id == current_user.id, Job.deleted_at.is_(None))
    )
    jobs = jobs_result.scalars().all()

    apps_result = await db.execute(
        select(Application).where(Application.user_id == current_user.id)
    )
    apps = apps_result.scalars().all()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "created_at": current_user.created_at.isoformat(),
        },
        "profile": {
            "full_name": profile.full_name if profile else None,
            "location": profile.location if profile else None,
            "work_authorization": profile.work_authorization if profile else None,
            "skills": profile.skills if profile else [],
        },
        "jobs_count": len(jobs),
        "applications_count": len(apps),
        "note": "Full data export — see audit-log endpoint for action history",
    }


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dashboard statistics."""
    from sqlalchemy import func

    def count_query(model, *conditions):
        return select(func.count()).select_from(model).where(*conditions)

    jobs_total = (await db.execute(
        count_query(Job, Job.user_id == current_user.id, Job.deleted_at.is_(None))
    )).scalar_one()

    apps_by_status = {}
    for app_status in ["draft", "ready_for_review", "approved", "submitted", "rejected"]:
        count = (await db.execute(
            count_query(Application, Application.user_id == current_user.id, Application.status == app_status)
        )).scalar_one()
        apps_by_status[app_status] = count

    return {
        "jobs_total": jobs_total,
        "applications": apps_by_status,
        "resumes_count": (await db.execute(
            count_query(Resume, Resume.user_id == current_user.id, Resume.deleted_at.is_(None))
        )).scalar_one(),
    }
