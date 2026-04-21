"""
Job parser service — no LLM required.

Fetches raw HTML from a URL (or accepts raw text), then uses regex + keyword
patterns to extract structured job data. Fast, free, and deterministic.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── Output schema (unchanged — same shape as before) ─────────────────────────

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
    parse_rationale: str = "regex"


# ── Skill keyword bank (tech + professional) ──────────────────────────────────

_SKILLS: list[str] = [
    # Languages
    "python", "javascript", "typescript", "java", "kotlin", "swift", "go", "golang",
    "rust", "c++", "c#", "ruby", "php", "scala", "r", "matlab", "bash", "shell",
    "powershell", "perl", "dart", "elixir", "haskell", "clojure", "lua",
    # Web / frontend
    "react", "next.js", "nextjs", "vue", "angular", "svelte", "html", "css", "sass",
    "tailwind", "bootstrap", "webpack", "vite", "jquery", "graphql", "rest", "api",
    # Backend / infra
    "node.js", "nodejs", "django", "flask", "fastapi", "spring", "rails", "express",
    "laravel", "phoenix", "gin", "fiber",
    # Data / ML
    "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "spark",
    "hadoop", "dbt", "airflow", "mlflow", "huggingface", "llm", "nlp", "machine learning",
    "deep learning", "computer vision", "data science", "data engineering", "etl",
    # Cloud / devops
    "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "terraform", "ansible",
    "jenkins", "github actions", "ci/cd", "linux", "unix", "nginx", "kafka",
    "rabbitmq", "celery", "redis", "elasticsearch",
    # Databases
    "postgresql", "postgres", "mysql", "sqlite", "mongodb", "dynamodb", "cassandra",
    "redis", "snowflake", "bigquery", "redshift", "oracle", "sql server",
    # Mobile
    "ios", "android", "react native", "flutter", "expo",
    # Tools / methodologies
    "git", "github", "gitlab", "jira", "agile", "scrum", "devops", "microservices",
    "rest api", "grpc", "oauth", "jwt", "tdd", "bdd", "unit testing",
    # Design
    "figma", "sketch", "adobe xd", "ui/ux", "ux design",
    # Business / soft
    "product management", "project management", "leadership", "communication",
    "teamwork", "mentoring", "cross-functional",
]

_SKILL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(_SKILLS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_skills(text: str) -> tuple[list[str], list[str]]:
    """Split skills into required vs preferred based on section context."""
    required: set[str] = set()
    preferred: set[str] = set()
    text_lower = text.lower()

    # Identify preferred / nice-to-have sections
    pref_section = re.search(
        r"(preferred|nice.to.have|bonus|plus|desirable|optional)(.*?)"
        r"(required|must|qualifications|responsibilities|$)",
        text_lower, re.DOTALL
    )
    pref_text = pref_section.group(2) if pref_section else ""

    for match in _SKILL_PATTERN.finditer(text):
        skill = match.group(0).lower()
        if pref_text and skill in pref_text:
            preferred.add(skill)
        else:
            required.add(skill)

    # Deduplicate preferred vs required
    preferred -= required
    return sorted(required), sorted(preferred)


def _extract_experience(text: str) -> tuple[int | None, int | None]:
    patterns = [
        r"(\d+)\+?\s*(?:to|-)\s*(\d+)\s*years?",    # "3-5 years"
        r"(\d+)\+\s*years?",                           # "3+ years"
        r"at\s+least\s+(\d+)\s*years?",               # "at least 3 years"
        r"minimum\s+(\d+)\s*years?",                   # "minimum 3 years"
        r"(\d+)\s*years?\s+of\s+experience",           # "5 years of experience"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            groups = [g for g in m.groups() if g]
            if len(groups) == 2:
                return int(groups[0]), int(groups[1])
            if len(groups) == 1:
                n = int(groups[0])
                return n, None
    return None, None


def _extract_salary(text: str) -> tuple[int | None, int | None, str]:
    m = re.search(
        r"\$\s?([\d,]+)[kK]?\s*(?:[-–to]+\s*\$?\s*([\d,]+)[kK]?)?",
        text
    )
    if m:
        def parse_amount(s: str) -> int:
            s = s.replace(",", "")
            n = int(s)
            return n * 1000 if n < 1000 else n

        lo = parse_amount(m.group(1))
        hi = parse_amount(m.group(2)) if m.group(2) else None
        return lo, hi, "USD"
    return None, None, "USD"


def _extract_remote(text: str) -> str:
    t = text.lower()
    if re.search(r"\bfully\s+remote\b|\bremote.first\b|\bwork\s+from\s+(anywhere|home)\b", t):
        return "remote"
    if re.search(r"\bhybrid\b", t):
        return "hybrid"
    if re.search(r"\bon.?site\b|\bin.?office\b|\bon.?premises\b", t):
        return "onsite"
    return "unknown"


def _extract_sponsorship(text: str) -> str:
    t = text.lower()
    if re.search(r"(visa\s+sponsorship\s+(is\s+)?(available|provided|offered)|we\s+(do\s+)?sponsor)", t):
        return "yes"
    if re.search(
        r"(must\s+be\s+(authorized|eligible)\s+to\s+work|no\s+sponsorship|"
        r"cannot\s+sponsor|will\s+not\s+sponsor|not\s+eligible\s+to\s+sponsor)",
        t,
    ):
        return "no"
    return "unknown"


def _extract_location(text: str) -> str:
    # Common "Location: X" / "City, ST" patterns
    m = re.search(r"(?:location|city|office)[:\s]+([A-Z][a-zA-Z ]+(?:,\s*[A-Z]{2})?)", text)
    if m:
        return m.group(1).strip()
    # City, State pattern near top of posting
    m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)*),\s*([A-Z]{2})\b", text)
    if m:
        return m.group(0)
    return ""


def _extract_title(text: str, url: str = "") -> str:
    """Try multiple heuristics to get a clean job title from text."""
    patterns = [
        r"(?:job\s+title|position|role)[:\s]+([^\n\r|]{3,60})",
        r"^#+\s*(.{5,60})\s*$",   # markdown heading
        r"^([A-Z][A-Za-z /\-&,]+(?:Engineer|Developer|Manager|Designer|Analyst|Scientist|Architect|Lead|Director|Intern))\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            title = m.group(1).strip().rstrip("|–-—").strip()
            if 3 < len(title) < 80:
                return title

    # Fallback: first non-empty line that looks like a title
    for line in text.splitlines()[:10]:
        line = line.strip()
        if 5 < len(line) < 80 and not line.startswith("http"):
            return line
    return ""


def _extract_company(text: str, url: str = "") -> str:
    m = re.search(r"(?:company|employer|organization|employer\s+name)[:\s]+([^\n\r]{2,60})", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Try to extract from known ATS URL patterns
    ats_patterns = [
        r"greenhouse\.io/([^/]+)/",
        r"lever\.co/([^/]+)/",
        r"ashbyhq\.com/([^/]+)/",
        r"([^.]+)\.myworkdayjobs\.com",
        r"jobs\.([^.]+)\.com",
    ]
    for pat in ats_patterns:
        m = re.search(pat, url, re.IGNORECASE)
        if m:
            return m.group(1).replace("-", " ").title()
    return ""


def _extract_questions(text: str) -> list[ApplicationQuestion]:
    """Detect explicit application questions in the posting."""
    from app.services.questionnaire import classify_question_type

    question_patterns = [
        r"(?:are|do|have|will|can|would)\s+you\s+[^?]{5,80}\?",
        r"(?:please\s+)?(?:describe|explain|tell\s+us|share)[^?]{5,100}\?",
        r"(?:what\s+is\s+your)[^?]{5,80}\?",
        r"(?:how\s+many)[^?]{5,80}\?",
    ]
    found: list[ApplicationQuestion] = []
    seen: set[str] = set()

    for pat in question_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            q_text = m.group(0).strip()
            norm = q_text.lower()[:60]
            if norm not in seen and len(q_text) > 10:
                seen.add(norm)
                found.append(ApplicationQuestion(
                    question_text=q_text,
                    question_type=classify_question_type(q_text),
                    required=False,
                ))
    return found[:15]  # Cap at 15


# ── Main parsing functions ────────────────────────────────────────────────────

async def fetch_job_html(url: str) -> tuple[str, str]:
    """Fetch URL and return (raw_html, cleaned_text)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AutoJobApplier/1.0)",
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
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return html, text


def parse_job_from_text(text: str, url: str = "") -> ParsedJob:
    """
    Pure-regex extraction — no LLM, no external API.
    Returns a ParsedJob with all fields populated from pattern matching.
    """
    required_skills, preferred_skills = _extract_skills(text)
    exp_min, exp_max = _extract_experience(text)
    sal_min, sal_max, sal_cur = _extract_salary(text)

    job = ParsedJob(
        title=_extract_title(text, url),
        company=_extract_company(text, url),
        location=_extract_location(text),
        remote_policy=_extract_remote(text),
        description=text[:5000],
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        years_experience_min=exp_min,
        years_experience_max=exp_max,
        sponsorship_hint=_extract_sponsorship(text),
        salary_min=sal_min,
        salary_max=sal_max,
        salary_currency=sal_cur,
        application_url=url or "",
        application_questions=_extract_questions(text),
        parse_rationale="regex",
    )

    logger.info(
        "job_parsed_regex",
        title=job.title or "(untitled)",
        company=job.company or "(unknown)",
        required_skills_count=len(required_skills),
    )
    return job


async def parse_job_from_url(url: str) -> tuple[str, str, ParsedJob]:
    """
    Fetch URL, extract text, parse with regex.
    Returns (raw_html, cleaned_text, parsed_job).
    """
    logger.info("parsing_job_url", url=url)
    raw_html, clean_text = await fetch_job_html(url)
    parsed = parse_job_from_text(clean_text, url)
    return raw_html, clean_text, parsed


def compute_dedup_hash(company: str, title: str, url: str) -> str:
    key = f"{(company or '').lower().strip()}|{(title or '').lower().strip()}|{_normalize_url(url)}"
    return hashlib.sha256(key.encode()).hexdigest()


def _normalize_url(url: str) -> str:
    url = re.sub(r"[?#].*$", "", (url or "").lower().strip())
    return url.rstrip("/")
