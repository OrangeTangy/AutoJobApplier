"""
Cover letter generator — no LLM required.

Produces a grounded cover letter from a simple template filled with real
data from the user's profile and job posting. Nothing is fabricated —
if a field is empty, it is omitted rather than invented.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class CoverLetterResult(BaseModel):
    cover_letter: str
    word_count: int = 0
    key_points: list[str] = Field(default_factory=list)
    rationale: str = ""


def generate_cover_letter(job_data: dict, profile_data: dict) -> CoverLetterResult:
    """
    Build a template-based cover letter.

    `job_data`: title, company, required_skills, description
    `profile_data`: full_name, work_history, education, skills, location
    """
    title = job_data.get("title") or "the open position"
    company = job_data.get("company") or "your company"
    full_name = profile_data.get("full_name") or "Applicant"
    skills: list[str] = profile_data.get("skills") or []
    work_history: list[dict] = profile_data.get("work_history") or []
    education: list[dict] = profile_data.get("education") or []
    location: str = profile_data.get("location") or ""
    required_skills: list[str] = job_data.get("required_skills") or []

    # Opening paragraph
    opening = (
        f"I am writing to express my interest in the {title} role at {company}. "
        f"My background and experience make me a strong candidate for this position."
    )

    # Experience paragraph — pull most recent role
    experience_para = ""
    if work_history:
        recent = work_history[0]
        exp_title = recent.get("title", "")
        exp_company = recent.get("company", "")
        bullets = recent.get("bullets") or []
        exp_lines = []
        if exp_title and exp_company:
            exp_lines.append(
                f"In my most recent role as {exp_title} at {exp_company}, I "
            )
        elif exp_title:
            exp_lines.append(f"As a {exp_title}, I ")
        else:
            exp_lines.append("In my previous role, I ")

        if bullets:
            exp_lines.append(bullets[0].lower().rstrip(".") + ".")
            if len(bullets) > 1:
                exp_lines.append(" I also " + bullets[1].lower().rstrip(".") + ".")
        experience_para = "".join(exp_lines)

    # Skills paragraph
    matched_skills = [s for s in skills if any(s.lower() in r.lower() for r in required_skills)]
    show_skills = matched_skills[:5] or skills[:5]
    skills_para = ""
    if show_skills:
        skills_list = ", ".join(show_skills[:-1])
        if len(show_skills) > 1:
            skills_list += f", and {show_skills[-1]}"
        else:
            skills_list = show_skills[0]
        skills_para = (
            f"I bring hands-on experience with {skills_list}, "
            f"which I believe directly supports the needs of this role."
        )

    # Education line
    edu_line = ""
    if education:
        top = education[0]
        degree = top.get("degree", "")
        field = top.get("field", "")
        inst = top.get("institution", "")
        if degree and inst:
            edu_line = f"I hold a {degree}" + (f" in {field}" if field else "") + (f" from {inst}." if inst else ".")

    # Closing paragraph
    closing = (
        f"I am enthusiastic about the opportunity to contribute to {company} "
        f"and would welcome the chance to discuss how my background aligns with your needs. "
        f"Thank you for your consideration."
    )

    # Assemble letter
    paragraphs = [opening]
    if experience_para:
        paragraphs.append(experience_para)
    if skills_para:
        paragraphs.append(skills_para)
    if edu_line:
        paragraphs.append(edu_line)
    paragraphs.append(closing)
    paragraphs.append(f"Sincerely,\n{full_name}")

    letter = "\n\n".join(paragraphs)
    word_count = len(letter.split())

    key_points = [p[:100] for p in paragraphs[:3]]

    logger.info(
        "cover_letter_generated_template",
        company=company,
        words=word_count,
        matched_skills=len(matched_skills),
    )

    return CoverLetterResult(
        cover_letter=letter,
        word_count=word_count,
        key_points=key_points,
        rationale="Template-based; grounded in profile work history and skills.",
    )
