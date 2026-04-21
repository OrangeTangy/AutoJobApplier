"""
Fit scorer — no LLM required.

Scores a job against a specific resume using:
1. Keyword overlap between job's required/preferred skills and resume text
2. Work-auth / sponsorship compatibility
3. Remote / location compatibility

Score 0-100:
  90-100: Strong match
  70-89:  Good match
  50-69:  Partial match
  30-49:  Weak match
  0-29:   Poor match
"""
from __future__ import annotations

import re
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class FitRationale(BaseModel):
    score: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    summary: str = ""


def score_job_fit(
    job_data: dict,
    profile_data: dict,
    resume_text: str = "",
) -> FitRationale:
    """
    Compute a fit score without any LLM calls.

    `job_data` keys: title, company, required_skills, preferred_skills,
                     years_experience_min, sponsorship_hint, remote_policy,
                     location, description
    `profile_data` keys: skills, work_authorization, requires_sponsorship,
                         willing_to_relocate, target_locations, work_history
    `resume_text`: plain text of the selected resume (for skill extraction)
    """
    required: list[str] = [s.lower() for s in (job_data.get("required_skills") or [])]
    preferred: list[str] = [s.lower() for s in (job_data.get("preferred_skills") or [])]

    # Combine profile skills + resume text for matching
    profile_skills = {s.lower() for s in (profile_data.get("skills") or [])}
    resume_skill_text = resume_text.lower()

    def has_skill(skill: str) -> bool:
        return skill in profile_skills or bool(re.search(re.escape(skill), resume_skill_text))

    matched = [s for s in required if has_skill(s)]
    missing_req = [s for s in required if not has_skill(s)]
    matched_pref = [s for s in preferred if has_skill(s)]
    missing_pref = [s for s in preferred if not has_skill(s)]

    red_flags: list[str] = []
    positive_signals: list[str] = []

    # ── Skill score (0–70 points) ─────────────────────────────────────────────
    if required:
        req_score = (len(matched) / len(required)) * 60
    else:
        req_score = 50.0   # No explicit requirements listed → neutral

    if preferred:
        pref_score = (len(matched_pref) / len(preferred)) * 10
    else:
        pref_score = 5.0

    skill_score = req_score + pref_score

    # ── Work authorization / sponsorship (0–15 points) ────────────────────────
    auth_score = 0.0
    sponsorship_hint = (job_data.get("sponsorship_hint") or "unknown").lower()
    requires_sponsorship = profile_data.get("requires_sponsorship", False)
    work_auth = (profile_data.get("work_authorization") or "").lower()

    if sponsorship_hint == "no" and requires_sponsorship:
        red_flags.append("Job offers no sponsorship but you require it")
        auth_score = 0
    elif sponsorship_hint == "yes" and requires_sponsorship:
        positive_signals.append("Job offers visa sponsorship")
        auth_score = 15
    elif not requires_sponsorship:
        positive_signals.append("No sponsorship needed")
        auth_score = 15
    else:
        auth_score = 7  # Unknown — neutral

    # ── Remote / location (0–15 points) ──────────────────────────────────────
    remote_score = 0.0
    remote_policy = (job_data.get("remote_policy") or "unknown").lower()
    willing_to_relocate = profile_data.get("willing_to_relocate", False)
    target_locations: list[str] = [
        loc.lower() for loc in (profile_data.get("target_locations") or [])
    ]
    job_location = (job_data.get("location") or "").lower()

    if remote_policy == "remote":
        positive_signals.append("Fully remote position")
        remote_score = 15
    elif remote_policy == "hybrid":
        remote_score = 10
        if target_locations and not any(loc in job_location for loc in target_locations):
            if not willing_to_relocate:
                red_flags.append(f"Hybrid role in {job_location!r} — outside your target locations")
                remote_score = 5
    elif remote_policy == "onsite":
        if target_locations and any(loc in job_location for loc in target_locations):
            positive_signals.append("On-site location matches your targets")
            remote_score = 15
        elif willing_to_relocate:
            positive_signals.append("Willing to relocate")
            remote_score = 10
        else:
            red_flags.append(f"On-site role in {job_location!r} — outside your target locations")
            remote_score = 0
    else:
        remote_score = 7  # Unknown — neutral

    # ── Experience level check ────────────────────────────────────────────────
    exp_min = job_data.get("years_experience_min")
    if exp_min:
        # Count years from work history
        total_years = _estimate_years_experience(profile_data.get("work_history") or [])
        if total_years < exp_min - 2:
            red_flags.append(
                f"Job requires {exp_min}+ years; estimated ~{total_years} years in profile"
            )
        elif total_years >= exp_min:
            positive_signals.append(
                f"Experience level matches ({total_years} estimated vs {exp_min}+ required)"
            )

    # ── Final score ───────────────────────────────────────────────────────────
    raw = skill_score + auth_score + remote_score
    score = max(0, min(100, round(raw)))

    # Penalty for major red flags
    if len(red_flags) >= 2:
        score = max(0, score - 10)

    # Build summary
    if score >= 80:
        verdict = "Strong match"
    elif score >= 65:
        verdict = "Good match"
    elif score >= 45:
        verdict = "Partial match"
    elif score >= 30:
        verdict = "Weak match"
    else:
        verdict = "Poor match"

    req_pct = f"{len(matched)}/{len(required)}" if required else "n/a"
    summary = (
        f"{verdict} — {req_pct} required skills matched"
        + (f"; {len(matched_pref)}/{len(preferred)} preferred" if preferred else "")
        + (f"; ⚠ {', '.join(red_flags)}" if red_flags else "")
    )

    logger.info(
        "job_scored_keyword",
        score=score,
        matched=len(matched),
        missing_req=len(missing_req),
        red_flags=len(red_flags),
    )

    return FitRationale(
        score=score,
        matched_skills=matched,
        missing_required_skills=missing_req,
        missing_preferred_skills=missing_pref,
        red_flags=red_flags,
        positive_signals=positive_signals,
        summary=summary,
    )


def _estimate_years_experience(work_history: list[dict]) -> int:
    """Rough year count from work_history entries with start_date / end_date."""
    import datetime
    now = datetime.date.today().year
    total = 0
    for entry in work_history:
        try:
            start = int(str(entry.get("start_date", ""))[:4])
            end_raw = str(entry.get("end_date", ""))
            end = now if not end_raw or "present" in end_raw.lower() else int(end_raw[:4])
            total += max(0, end - start)
        except (ValueError, TypeError):
            pass
    return total
