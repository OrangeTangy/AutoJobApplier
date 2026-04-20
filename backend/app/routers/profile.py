from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserProfile
from app.routers.deps import get_current_user
from app.schemas.profile import ProfileOut, ProfileUpdate
from app.utils.audit import write_audit
from app.utils.encryption import decrypt, encrypt

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    profile = await _get_profile_or_404(current_user.id, db)
    profile.phone = decrypt(profile.phone) if profile.phone else None
    return profile


@router.put("", response_model=ProfileOut)
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    profile = await _get_profile_or_404(current_user.id, db)

    for field, value in body.model_dump(exclude_none=True).items():
        if field == "phone" and value:
            value = encrypt(value)
        setattr(profile, field, value)

    await write_audit(
        db,
        action="profile_updated",
        actor="user",
        user_id=current_user.id,
        resource_type="user_profile",
        resource_id=profile.id,
    )
    await db.flush()
    profile.phone = decrypt(profile.phone) if profile.phone else None
    return profile


async def _get_profile_or_404(user_id, db: AsyncSession) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found — complete registration first")
    return profile
