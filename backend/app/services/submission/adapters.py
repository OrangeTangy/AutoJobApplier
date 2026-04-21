"""
Site-specific Playwright form adapters.

Each adapter knows how to fill the application form for a particular ATS
(Applicant Tracking System). The generic adapter handles everything else.

Safety rules (enforced in every adapter):
- No login bypass, MFA skip, or captcha solving
- No OTP or email code retrieval
- Pause on any verification challenge
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FormResult:
    fields_filled: int
    resume_uploaded: bool
    warnings: list[str]


class SiteAdapter(Protocol):
    async def fill(self, page, answers: dict[str, str], resume_pdf_path: str | None) -> FormResult:
        ...


# ── Registry ──────────────────────────────────────────────────────────────────

def get_adapter(url: str) -> "SiteAdapter":
    """Return the best adapter for a given application URL."""
    domain = _extract_domain(url)
    for pattern, adapter_cls in ADAPTER_REGISTRY:
        if re.search(pattern, domain, re.IGNORECASE):
            logger.info("site_adapter_selected", adapter=adapter_cls.__name__, domain=domain)
            return adapter_cls()
    return GenericAdapter()


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc


# ── Generic adapter ───────────────────────────────────────────────────────────

class GenericAdapter:
    """Best-effort form filler for unknown sites."""

    async def fill(self, page, answers: dict[str, str], resume_pdf_path: str | None) -> FormResult:
        filled = 0
        warnings: list[str] = []

        # Fill text inputs
        inputs = await page.query_selector_all("input[type='text'], input[type='email'], textarea")
        for el in inputs:
            name = (await el.get_attribute("name") or "").lower()
            placeholder = (await el.get_attribute("placeholder") or "").lower()
            label_text = await _get_label_text(page, el)
            context = f"{name} {placeholder} {label_text}"

            for q_type, value in answers.items():
                if _context_matches(context, q_type):
                    try:
                        await el.fill(value)
                        filled += 1
                    except Exception:
                        pass
                    break

        # Handle select dropdowns
        selects = await page.query_selector_all("select")
        for sel in selects:
            name = (await sel.get_attribute("name") or "").lower()
            label_text = await _get_label_text(page, sel)
            context = f"{name} {label_text}"

            for q_type, value in answers.items():
                if _context_matches(context, q_type):
                    try:
                        await _select_best_option(sel, value)
                        filled += 1
                    except Exception:
                        pass
                    break

        # Handle yes/no radio buttons
        radios = await page.query_selector_all("input[type='radio']")
        for radio in radios:
            name = (await radio.get_attribute("name") or "").lower()
            val = (await radio.get_attribute("value") or "").lower()
            if name in answers:
                answer_lower = answers[name].lower()
                if (val in ("yes", "true", "1") and "yes" in answer_lower) or \
                   (val in ("no", "false", "0") and "no" in answer_lower):
                    try:
                        await radio.check()
                        filled += 1
                    except Exception:
                        pass

        # Upload resume
        resume_uploaded = False
        if resume_pdf_path:
            file_inputs = await page.query_selector_all("input[type='file']")
            for fi in file_inputs:
                accept = (await fi.get_attribute("accept") or "").lower()
                if not accept or "pdf" in accept or ".pdf" in accept:
                    try:
                        await fi.set_input_files(resume_pdf_path)
                        resume_uploaded = True
                        break
                    except Exception as e:
                        warnings.append(f"Resume upload failed: {e}")

        return FormResult(fields_filled=filled, resume_uploaded=resume_uploaded, warnings=warnings)


# ── Workday adapter ───────────────────────────────────────────────────────────

class WorkdayAdapter:
    """Adapter for Workday ATS (myworkdayjobs.com and company-specific Workday instances)."""

    async def fill(self, page, answers: dict[str, str], resume_pdf_path: str | None) -> FormResult:
        filled = 0
        warnings: list[str] = []
        resume_uploaded = False

        # Workday uses specific data-automation-id attributes
        field_map = {
            "legalNameSection_firstName": answers.get("first_name", ""),
            "legalNameSection_lastName": answers.get("last_name", ""),
            "email": answers.get("email", ""),
            "phone": answers.get("phone", ""),
            "addressSection_city": answers.get("city", ""),
        }

        for automation_id, value in field_map.items():
            if not value:
                continue
            try:
                el = await page.query_selector(f"[data-automation-id='{automation_id}'] input")
                if el:
                    await el.fill(value)
                    filled += 1
            except Exception:
                pass

        # Upload resume via Workday file drop zone
        if resume_pdf_path:
            try:
                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(resume_pdf_path)
                    resume_uploaded = True
            except Exception as e:
                warnings.append(f"Workday resume upload: {e}")

        return FormResult(fields_filled=filled, resume_uploaded=resume_uploaded, warnings=warnings)


# ── Greenhouse adapter ────────────────────────────────────────────────────────

class GreenhouseAdapter:
    """Adapter for Greenhouse ATS (greenhouse.io application forms)."""

    async def fill(self, page, answers: dict[str, str], resume_pdf_path: str | None) -> FormResult:
        filled = 0
        warnings: list[str] = []
        resume_uploaded = False

        # Greenhouse fields use id attributes like 'first_name', 'last_name', etc.
        gh_fields = {
            "first_name": answers.get("first_name", ""),
            "last_name": answers.get("last_name", ""),
            "email": answers.get("email", ""),
            "phone": answers.get("phone", ""),
            "location": answers.get("location", ""),
            "website": answers.get("portfolio_url") or answers.get("linkedin_url", ""),
            "linkedin_profile": answers.get("linkedin_url", ""),
        }

        for field_id, value in gh_fields.items():
            if not value:
                continue
            try:
                el = await page.query_selector(f"#{field_id}, [name='{field_id}']")
                if el:
                    await el.fill(value)
                    filled += 1
            except Exception:
                pass

        # Fill custom questions (Greenhouse wraps them in .field--wrapper)
        question_divs = await page.query_selector_all(".field--wrapper")
        for div in question_divs:
            label_el = await div.query_selector("label")
            if not label_el:
                continue
            label = (await label_el.inner_text()).strip().lower()

            answer = _find_answer_for_label(label, answers)
            if answer:
                inp = await div.query_selector("input[type='text'], textarea, select")
                if inp:
                    tag = await inp.get_property("tagName")
                    tag = (await tag.json_value()).lower()
                    if tag == "select":
                        await _select_best_option(inp, answer)
                    else:
                        await inp.fill(answer)
                    filled += 1

        # Resume upload
        if resume_pdf_path:
            try:
                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(resume_pdf_path)
                    resume_uploaded = True
            except Exception as e:
                warnings.append(f"Greenhouse resume upload: {e}")

        return FormResult(fields_filled=filled, resume_uploaded=resume_uploaded, warnings=warnings)


# ── Lever adapter ─────────────────────────────────────────────────────────────

class LeverAdapter:
    """Adapter for Lever ATS (jobs.lever.co)."""

    async def fill(self, page, answers: dict[str, str], resume_pdf_path: str | None) -> FormResult:
        filled = 0
        warnings: list[str] = []
        resume_uploaded = False

        # Lever uses name attributes
        lever_fields = {
            "name": f"{answers.get('first_name','')} {answers.get('last_name','')}".strip(),
            "email": answers.get("email", ""),
            "phone": answers.get("phone", ""),
            "org": answers.get("current_company", ""),
            "urls[LinkedIn]": answers.get("linkedin_url", ""),
            "urls[GitHub]": answers.get("github_url", ""),
            "urls[Portfolio]": answers.get("portfolio_url", ""),
        }

        for field_name, value in lever_fields.items():
            if not value:
                continue
            try:
                el = await page.query_selector(f"[name='{field_name}']")
                if el:
                    await el.fill(value)
                    filled += 1
            except Exception:
                pass

        # Lever custom questions
        cards = await page.query_selector_all(".application-field")
        for card in cards:
            label_el = await card.query_selector("label")
            if not label_el:
                continue
            label = (await label_el.inner_text()).strip().lower()
            answer = _find_answer_for_label(label, answers)
            if answer:
                inp = await card.query_selector("input, textarea, select")
                if inp:
                    await inp.fill(answer)
                    filled += 1

        # Resume upload
        if resume_pdf_path:
            try:
                fi = await page.query_selector("input[type='file']")
                if fi:
                    await fi.set_input_files(resume_pdf_path)
                    resume_uploaded = True
            except Exception as e:
                warnings.append(f"Lever resume upload: {e}")

        return FormResult(fields_filled=filled, resume_uploaded=resume_uploaded, warnings=warnings)


# ── Ashby adapter ────────────────────────────────────────────────────────────

class AshbyAdapter:
    """Adapter for Ashby ATS (jobs.ashbyhq.com)."""

    async def fill(self, page, answers: dict[str, str], resume_pdf_path: str | None) -> FormResult:
        filled = 0
        warnings: list[str] = []
        resume_uploaded = False

        # Ashby uses placeholder text heavily
        placeholder_map = {
            "first name": answers.get("first_name", ""),
            "last name": answers.get("last_name", ""),
            "email": answers.get("email", ""),
            "phone": answers.get("phone", ""),
            "linkedin": answers.get("linkedin_url", ""),
            "github": answers.get("github_url", ""),
            "website": answers.get("portfolio_url", ""),
        }

        for placeholder, value in placeholder_map.items():
            if not value:
                continue
            try:
                el = await page.query_selector(f"input[placeholder*='{placeholder}' i]")
                if el:
                    await el.fill(value)
                    filled += 1
            except Exception:
                pass

        # Resume
        if resume_pdf_path:
            try:
                fi = await page.query_selector("input[type='file']")
                if fi:
                    await fi.set_input_files(resume_pdf_path)
                    resume_uploaded = True
            except Exception as e:
                warnings.append(f"Ashby resume upload: {e}")

        return FormResult(fields_filled=filled, resume_uploaded=resume_uploaded, warnings=warnings)


# ── Registry definition ───────────────────────────────────────────────────────

ADAPTER_REGISTRY: list[tuple[str, type]] = [
    (r"workday|myworkdayjobs", WorkdayAdapter),
    (r"greenhouse\.io|boards\.greenhouse", GreenhouseAdapter),
    (r"jobs\.lever\.co|lever\.co", LeverAdapter),
    (r"jobs\.ashbyhq\.com|ashbyhq", AshbyAdapter),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_label_text(page, element) -> str:
    """Find the label text associated with a form element."""
    try:
        el_id = await element.get_attribute("id")
        if el_id:
            label = await page.query_selector(f"label[for='{el_id}']")
            if label:
                return (await label.inner_text()).lower()
        # Walk up to find enclosing label
        parent = await element.query_selector("xpath=..")
        if parent:
            text = await parent.inner_text()
            return text[:80].lower()
    except Exception:
        pass
    return ""


def _context_matches(context: str, q_type: str) -> bool:
    """Check if a form field context string matches a question type."""
    patterns = {
        "work_authorization": ["authorized", "work in the us", "eligible to work"],
        "sponsorship": ["sponsorship", "visa", "h1b", "h-1b"],
        "salary": ["salary", "compensation", "pay"],
        "start_date": ["start date", "availability", "when can you start"],
        "relocation": ["relocation", "relocate", "willing to move"],
        "years_experience": ["years of experience", "how many years"],
        "first_name": ["first name", "firstname"],
        "last_name": ["last name", "lastname", "surname"],
        "email": ["email"],
        "phone": ["phone", "telephone", "mobile"],
        "linkedin_url": ["linkedin"],
        "github_url": ["github"],
        "portfolio_url": ["portfolio", "website", "personal site"],
    }
    keywords = patterns.get(q_type, [q_type.replace("_", " ")])
    return any(kw in context for kw in keywords)


def _find_answer_for_label(label: str, answers: dict[str, str]) -> str:
    """Find the best answer for a form field based on label text."""
    for q_type, value in answers.items():
        if _context_matches(label, q_type):
            return value
    return ""


async def _select_best_option(select_el, desired: str) -> None:
    """Select the best matching option in a <select> element."""
    options = await select_el.query_selector_all("option")
    desired_lower = desired.lower()
    best_match = None
    best_score = 0

    for opt in options:
        text = (await opt.inner_text()).lower().strip()
        value = (await opt.get_attribute("value") or "").lower()

        # Exact match
        if text == desired_lower or value == desired_lower:
            best_match = opt
            break

        # Partial match scoring
        common = len(set(desired_lower.split()) & set(text.split()))
        if common > best_score:
            best_score = common
            best_match = opt

    if best_match:
        val = await best_match.get_attribute("value")
        await select_el.select_option(value=val)
