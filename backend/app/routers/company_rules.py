from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import CompanyRule, User
from app.routers.deps import get_current_user
from app.utils.audit import write_audit

router = APIRouter(prefix="/company-rules", tags=["company-rules"])


class CompanyRuleCreate(BaseModel):
    company: str
    rule_type: str    # 'blacklist' | 'allowlist' | 'cooldown'
    reason: str | None = None
    cooldown_days: int | None = None


class CompanyRuleOut(BaseModel):
    id: uuid.UUID
    company: str
    rule_type: str
    reason: str | None
    cooldown_days: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CompanyRuleOut])
async def list_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyRule]:
    result = await db.execute(
        select(CompanyRule).where(CompanyRule.user_id == current_user.id)
        .order_by(CompanyRule.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=CompanyRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: CompanyRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyRule:
    if body.rule_type not in ("blacklist", "allowlist", "cooldown"):
        raise HTTPException(status_code=400, detail="rule_type must be blacklist, allowlist, or cooldown")

    if body.rule_type == "cooldown" and not body.cooldown_days:
        raise HTTPException(status_code=400, detail="cooldown_days required for cooldown rules")

    # Check if rule already exists
    existing = await db.execute(
        select(CompanyRule).where(
            CompanyRule.user_id == current_user.id,
            CompanyRule.company == body.company,
            CompanyRule.rule_type == body.rule_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Rule already exists for this company")

    rule = CompanyRule(
        user_id=current_user.id,
        company=body.company,
        rule_type=body.rule_type,
        reason=body.reason,
        cooldown_days=body.cooldown_days,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rule)
    await db.flush()

    await write_audit(
        db, action="company_rule_created", actor="user",
        user_id=current_user.id,
        metadata={"company": body.company, "rule_type": body.rule_type},
    )
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(CompanyRule).where(
            CompanyRule.id == rule_id,
            CompanyRule.user_id == current_user.id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)


async def check_company_rules(
    db: AsyncSession,
    user_id: uuid.UUID,
    company: str,
) -> tuple[bool, str]:
    """
    Check if a company is blacklisted or in cooldown.
    Returns (allowed: bool, reason: str).
    """
    from datetime import timedelta

    result = await db.execute(
        select(CompanyRule).where(
            CompanyRule.user_id == user_id,
            CompanyRule.company.ilike(company),
        )
    )
    rules = result.scalars().all()

    for rule in rules:
        if rule.rule_type == "blacklist":
            return False, f"{company} is blacklisted: {rule.reason or 'no reason given'}"

        if rule.rule_type == "cooldown" and rule.cooldown_days:
            # Check when last application was submitted
            from app.models.application import Application
            from app.models.job import Job

            last_app = await db.execute(
                select(Application)
                .join(Job, Application.job_id == Job.id)
                .where(
                    Application.user_id == user_id,
                    Job.company.ilike(company),
                    Application.status == "submitted",
                )
                .order_by(Application.submitted_at.desc())
                .limit(1)
            )
            last = last_app.scalar_one_or_none()
            if last and last.submitted_at:
                cooldown_end = last.submitted_at + timedelta(days=rule.cooldown_days)
                if datetime.now(timezone.utc) < cooldown_end:
                    days_left = (cooldown_end - datetime.now(timezone.utc)).days
                    return False, f"{company} in cooldown — {days_left} days remaining"

    return True, "ok"
