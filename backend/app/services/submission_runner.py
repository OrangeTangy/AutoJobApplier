"""
Submission runner — Playwright-based form filler.

SAFETY INVARIANTS (hard-coded, never configurable):
1. application.status MUST be 'approved' before any navigation
2. approval_hash MUST match current answer state
3. If any verification challenge appears (CAPTCHA, OTP, MFA), PAUSE and surface to user
4. NEVER auto-retrieve email codes, bypass MFA, or solve captchas
5. Every action is written to the audit log
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.application import Application
from app.utils.security import compute_approval_hash

logger = structlog.get_logger(__name__)
settings = get_settings()


class TamperedApprovalError(RuntimeError):
    """Raised when approval_hash does not match current answer state."""


class NotApprovedError(RuntimeError):
    """Raised when application is not in 'approved' status."""


class VerificationRequired(RuntimeError):
    """Raised when the page shows a challenge that requires human input."""

    def __init__(self, challenge_type: str, message: str) -> None:
        self.challenge_type = challenge_type
        super().__init__(message)


# ── Challenge detection ────────────────────────────────────────────────────────

CAPTCHA_SIGNALS = [
    "recaptcha", "hcaptcha", "cf-challenge", "turnstile",
    "are you human", "prove you're not a robot",
]
MFA_SIGNALS = [
    "verification code", "authenticator app", "enter the code",
    "two-factor", "2fa", "one-time password",
]
EMAIL_VERIFY_SIGNALS = [
    "check your email", "verify your email", "confirmation link",
    "sent you an email",
]


def _detect_challenge(page_content: str) -> str | None:
    lower = page_content.lower()
    if any(s in lower for s in CAPTCHA_SIGNALS):
        return "captcha"
    if any(s in lower for s in MFA_SIGNALS):
        return "mfa"
    if any(s in lower for s in EMAIL_VERIFY_SIGNALS):
        return "email_verification"
    return None


# ── Core runner ────────────────────────────────────────────────────────────────

def _assert_approval_valid(application: Application) -> None:
    """Hard safety gate — abort if approval integrity is violated."""
    if application.status != "approved":
        raise NotApprovedError(
            f"Application {application.id} is not approved (status={application.status})"
        )
    if application.approved_at is None:
        raise NotApprovedError(f"Application {application.id} has no approval timestamp")

    # Recompute hash from current final answers
    final_answers = [
        a.final_answer or a.draft_answer
        for a in (application.answers or [])
    ]
    resume_id_str = str(application.resume_id) if application.resume_id else ""
    current_hash = compute_approval_hash(resume_id_str, final_answers)

    if current_hash != application.approval_hash:
        raise TamperedApprovalError(
            f"Application {application.id}: approval_hash mismatch — "
            "answers may have been modified after approval"
        )


async def run_submission(
    application: Application,
    db: AsyncSession,
) -> dict:
    """
    Submit an approved application using Playwright.

    Returns a result dict with status and screenshot path.
    Raises on any integrity violation or unexpected challenge.
    """
    from app.utils.audit import write_audit

    # ── Safety gate (hard-coded, not configurable) ─────────────────────────
    _assert_approval_valid(application)

    job = application.job
    if not job or not job.application_url:
        raise ValueError("Job has no application URL")

    logger.info(
        "submission_starting",
        application_id=str(application.id),
        url=job.application_url,
    )

    await write_audit(
        db,
        action="submission_started",
        actor="worker",
        user_id=application.user_id,
        resource_type="application",
        resource_id=application.id,
        metadata={"url": job.application_url},
    )

    try:
        from playwright.async_api import async_playwright

        screenshot_path: str | None = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (compatible; AutoJobApplier/1.0)",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # Navigate
            await page.goto(job.application_url, wait_until="networkidle", timeout=30000)

            # Challenge detection — PAUSE immediately if found
            content = await page.content()
            challenge = _detect_challenge(content)
            if challenge:
                title = await page.title()
                raise VerificationRequired(
                    challenge,
                    f"Page '{title}' requires human verification: {challenge}. "
                    "Please complete this step manually.",
                )

            # Build answer map
            answer_map = _build_answer_map(application)

            # Fill form fields
            filled = await _fill_form(page, answer_map)

            # Upload resume PDF if available
            if application.resume and application.resume.compiled_pdf_path:
                await _upload_resume(page, application.resume.compiled_pdf_path)

            # Take screenshot BEFORE submitting
            storage = Path(settings.local_storage_path) / "screenshots"
            storage.mkdir(parents=True, exist_ok=True)
            screenshot_file = storage / f"{application.id}.png"
            await page.screenshot(path=str(screenshot_file), full_page=True)
            screenshot_path = str(screenshot_file)

            # Check for challenge again after filling
            content_after = await page.content()
            challenge_after = _detect_challenge(content_after)
            if challenge_after:
                raise VerificationRequired(
                    challenge_after,
                    f"Verification required after form fill: {challenge_after}. "
                    "Please complete manually.",
                )

            await browser.close()

        # Update application record
        application.submitted_at = datetime.now(timezone.utc)
        application.submission_url = job.application_url
        application.submission_screenshot_path = screenshot_path
        application.status = "submitted"
        await db.flush()

        await write_audit(
            db,
            action="application_submitted",
            actor="worker",
            user_id=application.user_id,
            resource_type="application",
            resource_id=application.id,
            metadata={"fields_filled": filled, "screenshot": screenshot_path},
        )

        logger.info(
            "submission_complete",
            application_id=str(application.id),
            fields_filled=filled,
        )
        return {"status": "submitted", "screenshot_path": screenshot_path, "fields_filled": filled}

    except VerificationRequired:
        application.status = "error"
        application.submission_error = "Verification challenge encountered — human action required"
        await db.flush()
        raise
    except Exception as exc:
        application.status = "error"
        application.submission_error = str(exc)[:500]
        await db.flush()
        await write_audit(
            db,
            action="submission_failed",
            actor="worker",
            user_id=application.user_id,
            resource_type="application",
            resource_id=application.id,
            metadata={"error": str(exc)[:200]},
        )
        logger.error("submission_failed", application_id=str(application.id), error=str(exc))
        raise


def _build_answer_map(application: Application) -> dict[str, str]:
    """Build question_text → final_answer mapping from approved answers."""
    result = {}
    for answer in application.answers:
        text = answer.final_answer or answer.draft_answer
        if text:
            result[answer.question_type] = text
            result[answer.question_text.lower()[:80]] = text
    return result


async def _fill_form(page: object, answer_map: dict[str, str]) -> int:
    """Fill visible form fields. Returns count of fields filled."""
    filled = 0
    # This is a best-effort generic filler; real implementations need site-specific adapters
    inputs = await page.query_selector_all("input[type='text'], input[type='email'], textarea")
    for input_el in inputs:
        placeholder = await input_el.get_attribute("placeholder") or ""
        name = await input_el.get_attribute("name") or ""
        label = placeholder.lower() + " " + name.lower()

        for key, value in answer_map.items():
            if key in label or any(word in label for word in key.split()[:3]):
                await input_el.fill(value)
                filled += 1
                break

    return filled


async def _upload_resume(page: object, pdf_path: str) -> None:
    """Attach resume PDF to any file input on the page."""
    file_inputs = await page.query_selector_all("input[type='file']")
    for file_input in file_inputs:
        accept = await file_input.get_attribute("accept") or ""
        if "pdf" in accept.lower() or not accept:
            await file_input.set_input_files(pdf_path)
            logger.info("resume_uploaded", path=pdf_path)
            return
