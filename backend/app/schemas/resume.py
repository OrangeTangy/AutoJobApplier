from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ResumeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    latex_source: str = Field(min_length=10)
    is_base: bool = False
    template_name: str | None = None


class BulletEditOut(BaseModel):
    section: str
    original: str
    tailored: str
    rationale: str


class ResumeOut(BaseModel):
    id: uuid.UUID
    name: str
    is_base: bool
    template_name: str | None
    word_count: int | None
    page_count: int | None
    compiled_pdf_path: str | None
    base_resume_id: uuid.UUID | None
    job_id: uuid.UUID | None
    tailoring_diff: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResumeTailorRequest(BaseModel):
    job_id: uuid.UUID
    base_resume_id: uuid.UUID
