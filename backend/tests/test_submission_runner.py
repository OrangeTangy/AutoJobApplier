"""Tests for the submission runner safety gates."""
from __future__ import annotations

import pytest

from app.services.submission_runner import (
    NotApprovedError,
    TamperedApprovalError,
    _assert_approval_valid,
    _detect_challenge,
)
from app.utils.security import compute_approval_hash


# ── Challenge detection ──────────────────────────────────────────────────────

class TestDetectChallenge:
    def test_recaptcha_detected(self):
        assert _detect_challenge("Please complete the recaptcha below") == "captcha"

    def test_hcaptcha_detected(self):
        assert _detect_challenge("hCaptcha verification required") == "captcha"

    def test_cf_challenge_detected(self):
        assert _detect_challenge("cf-challenge loading...") == "captcha"

    def test_mfa_detected(self):
        assert _detect_challenge("Enter your two-factor code") == "mfa"

    def test_otp_detected(self):
        assert _detect_challenge("Enter your one-time password") == "mfa"

    def test_email_verify_detected(self):
        assert _detect_challenge("Please check your email to verify") == "email_verification"

    def test_confirmation_link_detected(self):
        assert _detect_challenge("We sent you an email with a confirmation link") == "email_verification"

    def test_clean_page_returns_none(self):
        assert _detect_challenge("<html><body><form>Normal apply form</form></body></html>") is None

    def test_case_insensitive(self):
        assert _detect_challenge("RECAPTCHA REQUIRED") == "captcha"


# ── Approval validation ──────────────────────────────────────────────────────

class FakeAnswer:
    def __init__(self, final_answer=None, draft_answer=None):
        self.final_answer = final_answer
        self.draft_answer = draft_answer


class FakeApplication:
    def __init__(self, status, answers, resume_id=None, approval_hash=None, approved_at="2024-01-01"):
        self.id = "fake-id"
        self.status = status
        self.answers = answers
        self.resume_id = resume_id
        self.approval_hash = approval_hash
        self.approved_at = approved_at


class TestAssertApprovalValid:
    def _make_valid_app(self, answers_text=None):
        if answers_text is None:
            answers_text = ["yes", "3 years"]
        answers = [FakeAnswer(final_answer=a) for a in answers_text]
        hash_ = compute_approval_hash("", answers_text)
        return FakeApplication(
            status="approved",
            answers=answers,
            approval_hash=hash_,
        )

    def test_valid_application_passes(self):
        app = self._make_valid_app()
        # Should not raise
        _assert_approval_valid(app)

    def test_non_approved_status_raises(self):
        answers = [FakeAnswer(final_answer="yes")]
        hash_ = compute_approval_hash("", ["yes"])
        app = FakeApplication(status="draft", answers=answers, approval_hash=hash_)
        with pytest.raises(NotApprovedError):
            _assert_approval_valid(app)

    def test_missing_approved_at_raises(self):
        answers = [FakeAnswer(final_answer="yes")]
        hash_ = compute_approval_hash("", ["yes"])
        app = FakeApplication(status="approved", answers=answers, approval_hash=hash_, approved_at=None)
        with pytest.raises(NotApprovedError):
            _assert_approval_valid(app)

    def test_tampered_answer_raises(self):
        """Modifying an answer after approval must trigger TamperedApprovalError."""
        answers = [FakeAnswer(final_answer="yes")]
        original_hash = compute_approval_hash("", ["yes"])
        # Tamper: change the answer
        answers[0].final_answer = "no"
        app = FakeApplication(status="approved", answers=answers, approval_hash=original_hash)
        with pytest.raises(TamperedApprovalError):
            _assert_approval_valid(app)

    def test_added_answer_after_approval_raises(self):
        """Adding an answer after approval must trigger TamperedApprovalError."""
        original_hash = compute_approval_hash("", ["yes"])
        answers = [FakeAnswer(final_answer="yes"), FakeAnswer(final_answer="extra")]
        app = FakeApplication(status="approved", answers=answers, approval_hash=original_hash)
        with pytest.raises(TamperedApprovalError):
            _assert_approval_valid(app)

    def test_hash_uses_sorted_answers(self):
        """Hash must be order-independent (same answers in different order = same hash)."""
        texts = ["answer A", "answer B"]
        hash_ab = compute_approval_hash("", ["answer A", "answer B"])
        hash_ba = compute_approval_hash("", ["answer B", "answer A"])
        assert hash_ab == hash_ba

    def test_resume_id_change_raises(self):
        """Swapping resume after approval must trigger TamperedApprovalError."""
        answers = [FakeAnswer(final_answer="yes")]
        hash_ = compute_approval_hash("original-resume-id", ["yes"])
        app = FakeApplication(
            status="approved",
            answers=answers,
            resume_id="different-resume-id",
            approval_hash=hash_,
        )
        with pytest.raises(TamperedApprovalError):
            _assert_approval_valid(app)
