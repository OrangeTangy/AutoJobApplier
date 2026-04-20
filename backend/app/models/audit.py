from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPrimaryKey


class AuditLog(UUIDPrimaryKey, Base):
    """Append-only audit log. No UPDATE or DELETE should ever be issued on this table."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_user_action", "user_id", "action", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'user' | 'worker' | 'system'
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    # 'job_discovered' | 'job_parsed' | 'resume_tailored' | 'answer_generated'
    # | 'application_approved' | 'application_submitted' | 'answer_edited'
    # | 'login' | 'logout' | 'token_refreshed' | 'data_purge_requested' | ...
    resource_type: Mapped[str | None] = mapped_column(String(30))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
