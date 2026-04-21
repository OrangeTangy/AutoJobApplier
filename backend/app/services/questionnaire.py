"""
Questionnaire assistant — no LLM required.

Classifies application questions by type, then fills answers directly from
the user's profile. Sensitive questions are always flagged for mandatory
human review before approval.

No API key needed. All answers are grounded in the stored profile — nothing
is fabricated.
"""
from __future__ import annotations

import re
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── Types ─────────────────────────────────────────────────────────────────────

SENSITIVE_TYPES = {
    "work_authorization",
    "sponsorship",
    "demographic",
    "salary",
}

QUESTION_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("work_authorization", [
        r"authoriz", r"eligible to work", r"work in the u", r"legally permitted",
        r"right to work",
    ]),
    ("sponsorship", [
        r"sponsor", r"visa", r"h-?1b", r"h1b", r"opt", r"cpt",
    ]),
    ("relocation", [
        r"relocat", r"willing to move", r"open to relocation",
    ]),
    ("salary", [
        r"salary", r"compensation", r"pay expect", r"desired.*pay",
    ]),
    ("start_date", [
        r"start date", r"when can you start", r"earliest start", r"availability",
    ]),
    ("years_experience", [
        r"years.*(experience|exp)", r"how many years", r"level of experience",
    ]),
    ("education", [
        r"degree", r"gpa", r"graduation", r"major", r"institution",
    ]),
    ("demographic", [
        r"gender", r"ethnicity", r"race", r"veteran", r"disability",
        r"voluntary disclosure",
    ]),
    ("yes_no", [r"^(do|are|have|will|can|is|was|did) you"]),
    ("multiple_choice", [r"\(select one\)", r"choose one", r"which of the following"]),
]


class AnswerDraft(BaseModel):
    question_text: str
    question_type: str
    draft_answer: str
    confidence: str = "medium"   # 'high' | 'medium' | 'low'
    requires_review: bool = False
    sources: list[str] = Field(default_factory=list)
    rationale: str = ""


class AnswerBatch(BaseModel):
    answers: list[AnswerDraft] = Field(default_factory=list)


def classify_question_type(question_text: str) -> str:
    text_lower = question_text.lower()
    for q_type, patterns in QUESTION_TYPE_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return q_type
    return "short_answer"


def generate_answers(
    questions: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[AnswerDraft]:
    """
    Generate draft answers from the user's profile — no LLM required.

    For well-known question types (work auth, sponsorship, relocation, salary,
    start date), answers are pulled directly from profile fields with high
    confidence. Unknown questions get an empty draft flagged for human review.
    """
    if not questions:
        return []

    answers: list[AnswerDraft] = []

    for q in questions:
        text = q.get("question_text", "")
        q_type = q.get("question_type") or classify_question_type(text)
        if q_type == "unknown":
            q_type = classify_question_type(text)

        draft, confidence, sources, rationale, requires_review = _fill_from_profile(
            q_type, profile
        )

        # Sensitive types ALWAYS require human review regardless of confidence
        if q_type in SENSITIVE_TYPES:
            requires_review = True

        answers.append(AnswerDraft(
            question_text=text,
            question_type=q_type,
            draft_answer=draft,
            confidence=confidence,
            requires_review=requires_review,
            sources=sources,
            rationale=rationale,
        ))

    req_review = sum(1 for a in answers if a.requires_review)
    logger.info(
        "answers_generated_from_profile",
        count=len(answers),
        requiring_review=req_review,
        auto_filled=len(answers) - req_review,
    )
    return answers


def _fill_from_profile(
    q_type: str,
    profile: dict,
) -> tuple[str, str, list[str], str, bool]:
    """
    Returns (draft_answer, confidence, sources, rationale, requires_review).
    """
    match q_type:
        case "work_authorization":
            val = profile.get("work_authorization", "")
            if val:
                return (
                    val, "high",
                    ["profile.work_authorization"],
                    "Pulled directly from your profile work authorization field.",
                    True,   # Always review — legal / truthfulness critical
                )
            return ("", "low", [], "Work authorization not set in profile.", True)

        case "sponsorship":
            needs = profile.get("requires_sponsorship")
            if needs is True:
                answer = "Yes, I will require visa sponsorship."
            elif needs is False:
                answer = "No, I do not require visa sponsorship."
            else:
                answer = ""
            if answer:
                return (
                    answer, "high",
                    ["profile.requires_sponsorship"],
                    "Derived from requires_sponsorship flag in your profile.",
                    True,
                )
            return ("", "low", [], "Sponsorship requirement not set in profile.", True)

        case "relocation":
            willing = profile.get("willing_to_relocate")
            targets = profile.get("target_locations") or []
            if willing is True:
                answer = "Yes, I am willing to relocate."
                if targets:
                    answer += f" My preferred locations are: {', '.join(targets)}."
            elif willing is False:
                answer = "No, I am not currently open to relocation."
            else:
                answer = ""
            if answer:
                return (
                    answer, "high",
                    ["profile.willing_to_relocate", "profile.target_locations"],
                    "Derived from relocation preferences in your profile.",
                    False,
                )
            return ("", "low", [], "Relocation preference not set in profile.", True)

        case "salary":
            sal = profile.get("desired_salary")
            sal_min = profile.get("desired_salary_min")
            sal_max = profile.get("desired_salary_max")
            currency = profile.get("salary_currency", "USD")
            if sal_min and sal_max:
                answer = f"{currency} {sal_min:,} – {sal_max:,} per year"
            elif sal:
                answer = f"{currency} {sal:,} per year"
            else:
                answer = ""
            if answer:
                return (
                    answer, "high",
                    ["profile.desired_salary"],
                    "Pulled from desired salary range in your profile.",
                    True,  # Always review salary
                )
            return ("", "low", [], "Desired salary not set in profile.", True)

        case "start_date":
            start = profile.get("earliest_start_date", "")
            if start:
                return (
                    f"I am available to start on or after {start}.",
                    "high",
                    ["profile.earliest_start_date"],
                    "Pulled from earliest start date in your profile.",
                    False,
                )
            return (
                "I am flexible and can discuss a start date.",
                "medium",
                [],
                "No specific start date in profile — generic flexible response.",
                False,
            )

        case "years_experience":
            work_history = profile.get("work_history") or []
            years = _estimate_years(work_history)
            if years > 0:
                return (
                    f"I have approximately {years} years of relevant experience.",
                    "medium",
                    ["profile.work_history"],
                    "Estimated from work history entries in your profile.",
                    False,
                )
            return ("", "low", [], "Work history empty in profile.", True)

        case "education":
            edu = profile.get("education") or []
            if edu:
                top = edu[0]
                answer = f"{top.get('degree','')} in {top.get('field','')} from {top.get('institution','')} ({top.get('graduation_year','')})".strip()
                if len(answer) > 10:
                    return (
                        answer, "high",
                        ["profile.education"],
                        "Pulled from education entries in your profile.",
                        False,
                    )
            return ("", "low", [], "Education not set in profile.", True)

        case "demographic":
            return (
                "I prefer not to disclose.",
                "high",
                [],
                "Demographic questions are voluntary. Defaulting to 'prefer not to disclose'.",
                True,  # Always review demographic
            )

        case "yes_no":
            return ("", "low", [], "Yes/No question — please answer manually.", True)

        case _:
            # short_answer, multiple_choice, unknown
            return ("", "low", [], "Open-ended question — please fill in manually.", True)


def _estimate_years(work_history: list[dict]) -> int:
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
