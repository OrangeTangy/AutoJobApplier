from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from app.models.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.user import User


class Application(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        Index("idx_applications_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL")
    )
    cover_letter: Mapped[str | None] = mapped_column(Text)              # encrypted

    # State machine
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    # 'draft' | 'ready_for_review' | 'approved' | 'rejected' | 'submitted' | 'error'

    # Approval gate
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # SHA256(resume_id + all final answer texts) — validated before submission
    approval_hash: Mapped[str | None] = mapped_column(String(64))

    # Submission result
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_url: Mapped[str | None] = mapped_column(Text)
    submission_screenshot_path: Mapped[str | None] = mapped_column(Text)
    submission_error: Mapped[str | None] = mapped_column(Text)

    # Feedback
    outcome: Mapped[str | None] = mapped_column(String(30))
    # 'no_response' | 'rejected' | 'phone_screen' | 'technical' | 'offer' | 'accepted'
    user_notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    user: Mapped[User] = relationship(
        "User", back_populates="applications", foreign_keys=[user_id]
    )
    job: Mapped[Job] = relationship("Job", back_populates="application")
    resume: Mapped[Resume | None] = relationship("Resume")
    answers: Mapped[list[QuestionnaireAnswer]] = relationship(
        "QuestionnaireAnswer",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Application job={self.job_id} [{self.status}]>"


class QuestionnaireAnswer(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "questionnaire_answers"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 'work_authorization' | 'sponsorship' | 'relocation' | 'salary'
    # | 'start_date' | 'education' | 'years_experience' | 'demographic'
    # | 'short_answer' | 'yes_no' | 'multiple_choice' | 'unknown'

    draft_answer: Mapped[str] = mapped_column(Text, nullable=False)    # encrypted
    final_answer: Mapped[str | None] = mapped_column(Text)             # encrypted
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rationale: Mapped[str | None] = mapped_column(Text)
    user_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    application: Mapped[Application] = relationship("Application", back_populates="answers")

    def __repr__(self) -> str:
        return f"<Answer [{self.question_type}] conf={self.confidence}>"
