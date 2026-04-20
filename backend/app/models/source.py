from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.user import User


class IngestionSource(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ingestion_sources"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'gmail' | 'imap' | 'handshake' | 'manual_url'
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Sensitive fields inside config are encrypted at application layer
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)

    user: Mapped[User] = relationship("User", back_populates="ingestion_sources")
    jobs: Mapped[list[Job]] = relationship("Job", back_populates="source")

    def __repr__(self) -> str:
        return f"<IngestionSource {self.source_type}:{self.display_name}>"
