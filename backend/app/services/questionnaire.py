"""
Questionnaire assistant.

Classifies application questions and generates grounded answers
from the user's profile. Sensitive questions are flagged for mandatory review.
"""
from __future__ import annotations

import re
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.services.llm import get_llm_provider

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


_ANSWER_SYSTEM = """You are a job application assistant. Generate honest, grounded answers
to application questions based ONLY on the provided candidate profile.

Rules:
1. NEVER fabricate or exaggerate qualifications, skills, dates, or status
2. For work_authorization: use ONLY the exact authorization status from the profile
3. For demographic questions: note that these are voluntary; suggest "Prefer not to disclose"
   if no preference is set in the profile
4. Cite the source field (e.g., "user_profile.work_authorization") for each answer
5. Mark confidence:
   - high: answer is directly stated in profile
   - medium: answer can be inferred from profile with reasonable certainty
   - low: answer requires assumption or is ambiguous
6. Set requires_review=true for: work_authorization, sponsorship, demographic, salary questions"""


def classify_question_type(question_text: str) -> str:
    text_lower = question_text.lower()
    for q_type, patterns in QUESTION_TYPE_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return q_type
    return "short_answer"


def _build_answer_prompt(questions: list[dict], profile: dict) -> str:
    q_list = "\n".join(
        f"{i+1}. [{q.get('question_type','unknown')}] {q['question_text']}"
        for i, q in enumerate(questions)
    )
    return f"""Generate answers for these application questions.

<candidate_profile>
Full Name: {profile.get('full_name', '')}
Work Authorization: {profile.get('work_authorization', 'unknown')}
Requires Sponsorship: {profile.get('requires_sponsorship', False)}
Willing to Relocate: {profile.get('willing_to_relocate', False)}
Target Locations: {profile.get('target_locations', [])}
Desired Salary: {profile.get('desired_salary_min')}–{profile.get('desired_salary_max')} {profile.get('salary_currency','USD')}
Earliest Start Date: {profile.get('earliest_start_date', 'flexible')}
Education: {profile.get('education', [])}
Work History: {profile.get('work_history', [])}
Skills: {profile.get('skills', [])}
Custom Defaults: {profile.get('custom_qa_defaults', {})}
</candidate_profile>

<questions>
{q_list}
</questions>

Return JSON with "answers" array. Each element must include:
question_text, question_type, draft_answer, confidence, requires_review, sources (list of profile field paths), rationale."""


async def generate_answers(
    questions: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[AnswerDraft]:
    """Generate draft answers for a list of application questions."""
    if not questions:
        return []

    # Classify question types if not already set
    for q in questions:
        if not q.get("question_type") or q["question_type"] == "unknown":
            q["question_type"] = classify_question_type(q.get("question_text", ""))

    provider = get_llm_provider()
    prompt = _build_answer_prompt(questions, profile)

    try:
        batch = await provider.complete_structured(
            prompt, AnswerBatch, system=_ANSWER_SYSTEM, max_tokens=3000, temperature=0.1
        )
        answers = batch.answers

        # Enforce review flags for sensitive types regardless of LLM output
        for answer in answers:
            if answer.question_type in SENSITIVE_TYPES:
                answer.requires_review = True

        logger.info(
            "answers_generated",
            count=len(answers),
            requiring_review=sum(1 for a in answers if a.requires_review),
            model=provider.model_name,
        )
        return answers

    except Exception as exc:
        logger.error("answer_generation_failed", error=str(exc))
        raise
