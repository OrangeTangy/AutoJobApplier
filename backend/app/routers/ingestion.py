from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.source import IngestionSource
from app.models.user import User
from app.routers.deps import get_current_user
from app.utils.audit import write_audit
from app.utils.encryption import encrypt

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class SourceCreate(BaseModel):
    source_type: str   # 'imap' | 'gmail' | 'handshake'
    display_name: str
    config: dict       # Encrypted at storage; NEVER log this


class SourceOut(BaseModel):
    id: uuid.UUID
    source_type: str
    display_name: str
    is_active: bool
    last_polled_at: str | None

    model_config = {"from_attributes": True}


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IngestionSource:
    """Register an ingestion source. Credentials encrypted at rest."""
    if body.source_type not in ("imap", "gmail", "handshake", "manual_url"):
        raise HTTPException(status_code=400, detail="Invalid source_type")

    # Encrypt sensitive config fields
    safe_config = _encrypt_config(body.source_type, body.config)

    source = IngestionSource(
        user_id=current_user.id,
        source_type=body.source_type,
        display_name=body.display_name,
        config=safe_config,
    )
    db.add(source)
    await db.flush()

    await write_audit(
        db,
        action="ingestion_source_created",
        actor="user",
        user_id=current_user.id,
        resource_type="ingestion_source",
        resource_id=source.id,
        metadata={"type": body.source_type, "display_name": body.display_name},
    )
    return source


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IngestionSource]:
    result = await db.execute(
        select(IngestionSource).where(IngestionSource.user_id == current_user.id)
    )
    return list(result.scalars().all())


class SourceUpdate(BaseModel):
    is_active: bool | None = None
    display_name: str | None = None


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IngestionSource:
    """Toggle active state or rename a source."""
    result = await db.execute(
        select(IngestionSource).where(
            IngestionSource.id == source_id,
            IngestionSource.user_id == current_user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.is_active is not None:
        source.is_active = body.is_active
    if body.display_name is not None:
        source.display_name = body.display_name

    await db.flush()
    return source


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(IngestionSource).where(
            IngestionSource.id == source_id,
            IngestionSource.user_id == current_user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)

    await write_audit(
        db,
        action="ingestion_source_deleted",
        actor="user",
        user_id=current_user.id,
        resource_type="ingestion_source",
        resource_id=source_id,
    )


def _encrypt_config(source_type: str, config: dict) -> dict:
    """Encrypt sensitive fields in source config before storage."""
    SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "refresh_token", "access_token"}
    result = {}
    for key, value in config.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS) and isinstance(value, str):
            result[key] = encrypt(value)
        else:
            result[key] = value
    return result
