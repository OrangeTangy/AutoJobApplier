"""
Job parser service.

Fetches raw HTML from a URL (or accepts raw text), then uses the LLM to
extract structured job data. All fields are grounded in the raw job text —
nothing is fabricated.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.llm import get_llm_provider

logger = structlog.get_logger(__name__)


# ── Output schema ─────────────────────────────────────────────────────────────

class ApplicationQuestion(BaseModel):
    question_text: str
    question_type: str = "unknown"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class ParsedJob(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    remote_policy: str = "unknown"
    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    years_experience_min: int | None = None
    years_experience_max: int | None = None
    sponsorship_hint: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    deadline: str | None = None
    application_url: str = ""
    application_questions: list[ApplicationQuestion] = Field(default_factory=list)
    parse_rationale: str = ""


_PARSE_SYSTEM = """You are a structured data extractor. Given raw job posting text, extract the
fields exactly as they appear. Do NOT invent or infer information not present in the text.

For sponsorship_hint:
- 'yes' if the posting says visa sponsorship is available
- 'no' if the posting says no sponsorship or must be authorized
- 'unknown' if not mentioned

For remote_policy: 'remote', 'hybrid', 'onsite', or 'unknown'.

For application_questions: identify any explicit questions on the application form
(e.g. "Are you authorized to work in the US?", "What is your expected salary?")."""


def _build_parse_prompt(raw_text: str, url: str) -> str:
    return f"""Extract structured data from this job posting.

URL: {url}

<job_description>
{raw_text[:8000]}
</job_description>

Return a JSON object with all fields from the schema."""


async def fetch_job_html(url: str) -> tuple[str, str]:
    """Fetch URL and return (raw_html, cleaned_text)."""
    settings = get_settings()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AutoJobApplier/1.0; +https://github.com/user/autojobapplier)",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=headers,
        limits=httpx.Limits(max_connections=5),
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "lxml")
    # Remove scripts, styles, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return html, text


def compute_dedup_hash(company: str, title: str, url: str) -> str:
    key = f"{company.lower().strip()}|{title.lower().strip()}|{_normalize_url(url)}"
    return hashlib.sha256(key.encode()).hexdigest()


def _normalize_url(url: str) -> str:
    # Strip tracking params and fragments
    url = re.sub(r"[?#].*$", "", url.lower().strip())
    return url


async def parse_job_from_url(url: str) -> tuple[str, str, ParsedJob]:
    """
    Fetch URL, extract text, call LLM to parse.
    Returns (raw_html, cleaned_text, parsed_job).
    """
    logger.info("parsing_job_url", url=url)
    raw_html, clean_text = await fetch_job_html(url)
    parsed = await parse_job_from_text(clean_text, url)
    return raw_html, clean_text, parsed


async def parse_job_from_text(text: str, url: str = "") -> ParsedJob:
    """Call LLM to parse job text into structured fields."""
    provider = get_llm_provider()
    prompt = _build_parse_prompt(text, url)
    try:
        result = await provider.complete_structured(
            prompt, ParsedJob, system=_PARSE_SYSTEM, max_tokens=2048
        )
        if url and not result.application_url:
            result.application_url = url
        logger.info(
            "job_parsed",
            company=result.company,
            title=result.title,
            model=provider.model_name,
        )
        return result
    except Exception as exc:
        logger.error("job_parse_failed", url=url, error=str(exc))
        raise
