from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnswerEditRequest(BaseModel):
    final_answer: str = Field(min_length=0, max_length=5000)


class AnswerOut(BaseModel):
    id: uuid.UUID
    question_text: str
    question_type: str
    draft_answer: str
    final_answer: str | None
    confidence: str
    requires_review: bool
    sources: list
    rationale: str | None
    user_edited: bool
    approved: bool

    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID | None
    status: str
    approved_at: datetime | None
    submitted_at: datetime | None
    outcome: str | None
    user_notes: str | None
    created_at: datetime
    updated_at: datetime
    answers: list[AnswerOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ApplicationApproveRequest(BaseModel):
    notes: str | None = None


class ApplicationRejectRequest(BaseModel):
    reason: str | None = None


class OutcomeUpdateRequest(BaseModel):
    outcome: str
    notes: str | None = None
