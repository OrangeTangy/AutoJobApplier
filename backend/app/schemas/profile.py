from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class WorkHistoryEntry(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str
    degree: str
    field: str = ""
    gpa: str | None = None
    graduated_at: str | None = None
    in_progress: bool = False


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    work_authorization: str | None = None
    requires_sponsorship: bool | None = None
    desired_salary_min: int | None = None
    desired_salary_max: int | None = None
    salary_currency: str | None = None
    earliest_start_date: date | None = None
    willing_to_relocate: bool | None = None
    target_locations: list[str] | None = None
    education: list[dict[str, Any]] | None = None
    work_history: list[dict[str, Any]] | None = None
    skills: list[str] | None = None
    certifications: list[str] | None = None
    custom_qa_defaults: dict[str, str] | None = None


class ProfileOut(BaseModel):
    id: str
    user_id: str
    full_name: str
    phone: str | None
    location: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    work_authorization: str
    requires_sponsorship: bool
    desired_salary_min: int | None
    desired_salary_max: int | None
    salary_currency: str
    earliest_start_date: date | None
    willing_to_relocate: bool
    target_locations: list
    education: list
    work_history: list
    skills: list
    certifications: list
    custom_qa_defaults: dict

    model_config = {"from_attributes": True}
