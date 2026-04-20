from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl


class JobIngest(BaseModel):
    url: str = Field(description="Job posting URL to ingest")


class ApplicationQuestionOut(BaseModel):
    question_text: str
    question_type: str
    required: bool
    options: list[str] = Field(default_factory=list)


class FitRationaleOut(BaseModel):
    score: int
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    summary: str = ""


class JobOut(BaseModel):
    id: uuid.UUID
    title: str | None
    company: str | None
    location: str | None
    remote_policy: str | None
    description: str | None
    required_skills: list
    preferred_skills: list
    years_experience_min: int | None
    years_experience_max: int | None
    sponsorship_hint: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    deadline: date | None
    application_url: str | None
    application_questions: list
    fit_score: int | None
    fit_rationale: dict | None
    status: str
    discovered_at: datetime
    raw_url: str | None

    model_config = {"from_attributes": True}


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int
    page: int
    page_size: int


class JobFilters(BaseModel):
    status: str | None = None
    company: str | None = None
    min_fit_score: int | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
