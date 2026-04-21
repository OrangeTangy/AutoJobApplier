"""
Cover letter generator.

Produces a tailored cover letter grounded entirely in the user's profile
and work history. Never fabricates experience, titles, or dates.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from app.services.llm import get_llm_provider

logger = structlog.get_logger(__name__)


class CoverLetterResult(BaseModel):
    cover_letter: str
    word_count: int = 0
    key_points: list[str] = Field(default_factory=list)
    rationale: str = ""


_COVER_SYSTEM = """You are a professional cover letter writer. You write concise, compelling
cover letters (250–350 words) grounded ONLY in the candidate's provided work history,
education, and skills.

Rules:
1. NEVER invent experience, technologies, projects, dates, or achievements not in the profile
2. Do NOT use generic filler phrases like "I am a passionate team player"
3. Draw specific examples from work_history bullets
4. Address the specific role and company by name
5. Structure: hook (1 para) → relevant experience (2 para) → closing (1 para)
6. Output ONLY the cover letter text — no subject line, no metadata"""


def _build_cl_prompt(job_data: dict, profile_data: dict) -> str:
    work = "\n".join(
        f"  {e.get('title','')} @ {e.get('company','')} ({e.get('start_date','')}–{e.get('end_date','Present')}):\n"
        + "\n".join(f"    • {b}" for b in e.get("bullets", []))
        for e in profile_data.get("work_history", [])
    )
    edu = " | ".join(
        f"{e.get('degree','')} {e.get('field','')} from {e.get('institution','')}"
        for e in profile_data.get("education", [])
    )
    return f"""Write a cover letter for this candidate applying to this position.

<job>
Title: {job_data.get('title', 'Unknown')}
Company: {job_data.get('company', 'Unknown')}
Key Requirements: {job_data.get('required_skills', [])}
Description Excerpt: {str(job_data.get('description', ''))[:1500]}
</job>

<candidate>
Name: {profile_data.get('full_name', '')}
Education: {edu}
Work History:
{work or '  (none provided)'}
Skills: {', '.join(profile_data.get('skills', [])[:20])}
</candidate>

Write the cover letter now. 250–350 words. Address it to the hiring team at {job_data.get('company', 'the company')}."""


async def generate_cover_letter(job_data: dict, profile_data: dict) -> CoverLetterResult:
    """Generate a grounded cover letter for a job + profile combination."""
    provider = get_llm_provider()
    prompt = _build_cl_prompt(job_data, profile_data)

    resp = await provider.complete(
        prompt, system=_COVER_SYSTEM, max_tokens=1000, temperature=0.3
    )
    letter = resp.content.strip()
    words = len(letter.split())

    # Extract 3 key talking points
    lines = [l.strip() for l in letter.splitlines() if len(l.strip()) > 40]
    key_points = lines[:3] if len(lines) >= 3 else lines

    logger.info(
        "cover_letter_generated",
        company=job_data.get("company"),
        words=words,
        model=provider.model_name,
    )
    return CoverLetterResult(
        cover_letter=letter,
        word_count=words,
        key_points=key_points,
        rationale=f"Generated using {provider.model_name}; grounded in {len(profile_data.get('work_history',[]))} work entries",
    )
