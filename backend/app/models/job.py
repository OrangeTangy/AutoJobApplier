from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint,
)
from app.models.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.source import IngestionSource
    from app.models.user import User


class Job(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_hash"),
        Index("idx_jobs_user_status", "user_id", "status"),
        Index("idx_jobs_user_company", "user_id", "company"),
        Index("idx_jobs_fit_score", "user_id", "fit_score"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_sources.id", ondelete="SET NULL")
    )
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Raw
    raw_url: Mapped[str | None] = mapped_column(Text)
    raw_html: Mapped[str | None] = mapped_column(Text)
    raw_email_id: Mapped[str | None] = mapped_column(String(255))

    # Parsed fields
    title: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    remote_policy: Mapped[str | None] = mapped_column(String(20))
    # 'remote' | 'hybrid' | 'onsite' | 'unknown'
    description: Mapped[str | None] = mapped_column(Text)
    required_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    years_experience_min: Mapped[int | None] = mapped_column(Integer)
    years_experience_max: Mapped[int | None] = mapped_column(Integer)
    sponsorship_hint: Mapped[str | None] = mapped_column(String(20))
    # 'yes' | 'no' | 'unknown'
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    deadline: Mapped[date | None] = mapped_column(Date)
    application_url: Mapped[str | None] = mapped_column(Text)
    application_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    parse_rationale: Mapped[dict | None] = mapped_column(JSONB)

    # Scoring
    fit_score: Mapped[int | None] = mapped_column(SmallInteger)
    fit_rationale: Mapped[dict | None] = mapped_column(JSONB)

    # Status machine
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="new")
    parse_error: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="jobs")
    source: Mapped[IngestionSource | None] = relationship("IngestionSource", back_populates="jobs")
    application: Mapped[Application | None] = relationship(
        "Application", back_populates="job", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Job {self.company}/{self.title} [{self.status}]>"
