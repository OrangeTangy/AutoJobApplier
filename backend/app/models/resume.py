from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User


class Resume(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_base: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    latex_source: Mapped[str] = mapped_column(Text, nullable=False)     # encrypted
    compiled_pdf_path: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict | None] = mapped_column(JSONB)
    # {sections: {experience: [...], education: [...], skills: [...], projects: [...]}}

    template_name: Mapped[str | None] = mapped_column(String(50))
    word_count: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # For tailored variants — links back to base resume
    base_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    tailoring_diff: Mapped[dict | None] = mapped_column(JSONB)
    # [{section, original_bullet, tailored_bullet, rationale}]

    user: Mapped[User] = relationship("User", back_populates="resumes")
    base_resume: Mapped[Resume | None] = relationship(
        "Resume", remote_side="Resume.id", foreign_keys=[base_resume_id]
    )

    def __repr__(self) -> str:
        return f"<Resume {self.name} [base={self.is_base}]>"
