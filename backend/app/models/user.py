from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from app.models.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.source import IngestionSource


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    profile: Mapped[UserProfile | None] = relationship(
        "UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    resumes: Mapped[list[Resume]] = relationship(
        "Resume", back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan",
        foreign_keys="Application.user_id",
    )
    ingestion_sources: Mapped[list[IngestionSource]] = relationship(
        "IngestionSource", back_populates="user", cascade="all, delete-orphan"
    )
    company_rules: Mapped[list[CompanyRule]] = relationship(
        "CompanyRule", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class UserProfile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)                    # encrypted
    location: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    portfolio_url: Mapped[str | None] = mapped_column(Text)

    work_authorization: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )
    requires_sponsorship: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    desired_salary_min: Mapped[int | None] = mapped_column(Integer)
    desired_salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    earliest_start_date: Mapped[datetime | None] = mapped_column(Date)
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    target_locations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    education: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    work_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    certifications: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    custom_qa_defaults: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped[User] = relationship("User", back_populates="profile")


class CompanyRule(UUIDPrimaryKey, Base):
    __tablename__ = "company_rules"
    __table_args__ = (UniqueConstraint("user_id", "company", "rule_type"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'blacklist' | 'allowlist' | 'cooldown'
    reason: Mapped[str | None] = mapped_column(Text)
    cooldown_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="company_rules")
