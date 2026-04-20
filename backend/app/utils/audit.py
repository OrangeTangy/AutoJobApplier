from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = structlog.get_logger(__name__)


def _hash_payload(payload: dict) -> str:
    """SHA-256 of sanitized payload — strips any field named 'token', 'password', 'key'."""
    safe = {
        k: v for k, v in payload.items()
        if not any(s in k.lower() for s in ("token", "password", "key", "secret", "cred"))
    }
    return hashlib.sha256(json.dumps(safe, default=str, sort_keys=True).encode()).hexdigest()


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    actor: str = "system",
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    meta = metadata or {}
    entry = AuditLog(
        user_id=user_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_hash=_hash_payload(meta),
        metadata_=meta,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()   # get ID without committing
    logger.info(
        "audit",
        action=action,
        actor=actor,
        user_id=str(user_id) if user_id else None,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
    )
    return entry
