"""Tests for questionnaire classifier and answer generator."""
from __future__ import annotations

import pytest

from app.services.questionnaire import SENSITIVE_TYPES, classify_question_type, generate_answers


def test_classify_work_authorization():
    q = "Are you authorized to work in the United States?"
    assert classify_question_type(q) == "work_authorization"


def test_classify_sponsorship():
    q = "Will you now or in the future require visa sponsorship?"
    assert classify_question_type(q) == "sponsorship"


def test_classify_relocation():
    q = "Are you willing to relocate for this position?"
    assert classify_question_type(q) == "relocation"


def test_classify_salary():
    q = "What are your salary expectations?"
    assert classify_question_type(q) == "salary"


def test_classify_start_date():
    q = "What is your earliest available start date?"
    assert classify_question_type(q) == "start_date"


def test_classify_demographic():
    q = "Voluntary self-identification: gender, race/ethnicity"
    assert classify_question_type(q) == "demographic"


def test_classify_years_experience():
    q = "How many years of experience do you have with Python?"
    assert classify_question_type(q) == "years_experience"


def test_classify_unknown():
    q = "Tell me about a time you showed leadership."
    # Should fall through to short_answer
    result = classify_question_type(q)
    assert result in ("short_answer", "unknown")


def test_sensitive_types_include_key_categories():
    assert "work_authorization" in SENSITIVE_TYPES
    assert "sponsorship" in SENSITIVE_TYPES
    assert "demographic" in SENSITIVE_TYPES


@pytest.mark.asyncio
async def test_generate_answers_uses_mock():
    """generate_answers uses MockProvider when no API key is set."""
    questions = [
        {"question_text": "Are you authorized to work in the US?", "question_type": "work_authorization"},
        {"question_text": "What is your expected salary?", "question_type": "salary"},
    ]
    profile = {
        "full_name": "Jane Doe",
        "work_authorization": "citizen",
        "requires_sponsorship": False,
        "desired_salary_min": 120000,
        "desired_salary_max": 150000,
        "salary_currency": "USD",
        "willing_to_relocate": True,
        "target_locations": ["Remote"],
        "education": [],
        "work_history": [],
        "skills": ["Python", "TypeScript"],
        "custom_qa_defaults": {},
    }
    answers = await generate_answers(questions, profile)
    assert isinstance(answers, list)
    # All sensitive types should require review
    for answer in answers:
        if answer.question_type in SENSITIVE_TYPES:
            assert answer.requires_review is True
