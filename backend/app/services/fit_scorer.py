"""Fit scorer — compares job requirements against user profile."""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from app.services.llm import get_llm_provider

logger = structlog.get_logger(__name__)


class FitRationale(BaseModel):
    score: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    summary: str = ""


_SCORE_SYSTEM = """You are a job fit evaluator. Compare the job requirements against the
candidate profile and produce an honest, calibrated fit score from 0-100.

Scoring rubric:
- 90-100: Strong match; meets nearly all requirements; high chance of interview
- 70-89:  Good match; meets most requirements; some gaps but likely qualified
- 50-69:  Partial match; meets core requirements but has notable gaps
- 30-49:  Weak match; missing several key requirements
- 0-29:   Poor match; significant qualification gaps

Be honest — do NOT inflate scores. Identify red flags (e.g., requires clearance,
years_experience significantly above candidate, explicit sponsorship denial)."""


def _build_score_prompt(job_data: dict, profile_data: dict) -> str:
    return f"""Evaluate the fit between this job and this candidate.

<job>
Title: {job_data.get('title', 'Unknown')}
Company: {job_data.get('company', 'Unknown')}
Location: {job_data.get('location', '')} ({job_data.get('remote_policy', 'unknown')})
Required Skills: {job_data.get('required_skills', [])}
Preferred Skills: {job_data.get('preferred_skills', [])}
Years Experience (min): {job_data.get('years_experience_min')}
Sponsorship: {job_data.get('sponsorship_hint', 'unknown')}
Description excerpt: {str(job_data.get('description', ''))[:1500]}
</job>

<candidate>
Skills: {profile_data.get('skills', [])}
Work Authorization: {profile_data.get('work_authorization', 'unknown')}
Requires Sponsorship: {profile_data.get('requires_sponsorship', False)}
Willing to Relocate: {profile_data.get('willing_to_relocate', False)}
Target Locations: {profile_data.get('target_locations', [])}
Work History (titles): {[w.get('title','') for w in profile_data.get('work_history', [])]}
Education: {[f"{e.get('degree','')} {e.get('field','')}" for e in profile_data.get('education', [])]}
</candidate>

Return a JSON object with score (0-100), matched_skills, missing_required_skills,
missing_preferred_skills, red_flags, positive_signals, and summary."""


async def score_job_fit(job_data: dict, profile_data: dict) -> FitRationale:
    provider = get_llm_provider()
    prompt = _build_score_prompt(job_data, profile_data)
    try:
        result = await provider.complete_structured(
            prompt, FitRationale, system=_SCORE_SYSTEM, max_tokens=1024
        )
        logger.info(
            "job_scored",
            score=result.score,
            red_flags=len(result.red_flags),
            model=provider.model_name,
        )
        return result
    except Exception as exc:
        logger.error("fit_score_failed", error=str(exc))
        raise
