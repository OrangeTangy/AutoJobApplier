from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserProfile
from app.routers.deps import get_client_ip, get_current_user
from app.schemas.auth import LoginRequest, RegisterRequest, RefreshRequest, TokenResponse, UserOut
from app.utils.audit import write_audit
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger(__name__)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.flush()

    profile = UserProfile(user_id=user.id, full_name=body.full_name)
    db.add(profile)

    await write_audit(
        db,
        action="user_registered",
        actor="user",
        user_id=user.id,
        ip_address=get_client_ip(request),
    )
    logger.info("user_registered", user_id=str(user.id))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        await write_audit(
            db,
            action="login_failed",
            actor="user",
            ip_address=get_client_ip(request),
            metadata={"email": body.email},
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active or user.deleted_at:
        raise HTTPException(status_code=403, detail="Account inactive")

    await write_audit(
        db,
        action="login",
        actor="user",
        user_id=user.id,
        ip_address=get_client_ip(request),
    )
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")

    user_id = payload.get("sub")
    await write_audit(
        db,
        action="token_refreshed",
        actor="user",
        user_id=user_id,
    )
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await write_audit(db, action="logout", actor="user", user_id=current_user.id)
