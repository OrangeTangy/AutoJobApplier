"""
LaTeX resume parser.

Supports common resume templates: moderncv, awesome-cv, altacv, and plain article.
Extracts structured sections without executing any LaTeX code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatexBullet:
    text: str
    raw: str


@dataclass
class LatexEntry:
    title: str = ""
    organization: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    bullets: list[LatexBullet] = field(default_factory=list)
    raw: str = ""


@dataclass
class ParsedResume:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    summary: str = ""
    experience: list[LatexEntry] = field(default_factory=list)
    education: list[LatexEntry] = field(default_factory=list)
    projects: list[LatexEntry] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    raw_sections: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "linkedin": self.linkedin,
            "github": self.github,
            "website": self.website,
            "summary": self.summary,
            "experience": [_entry_to_dict(e) for e in self.experience],
            "education": [_entry_to_dict(e) for e in self.education],
            "projects": [_entry_to_dict(e) for e in self.projects],
            "skills": self.skills,
            "certifications": self.certifications,
        }


def _entry_to_dict(e: LatexEntry) -> dict:
    return {
        "title": e.title,
        "organization": e.organization,
        "location": e.location,
        "start_date": e.start_date,
        "end_date": e.end_date,
        "bullets": [b.text for b in e.bullets],
    }


# ── Regex helpers ─────────────────────────────────────────────────────────────

_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.MULTILINE)
_CMD_RE = re.compile(r"\\([a-zA-Z]+)\*?\s*(\{[^{}]*\}|\[[^\[\]]*\])*", re.DOTALL)
_BRACE_CONTENT = re.compile(r"\{([^{}]*)\}")

# Section headers — covers most templates
_SECTION_RE = re.compile(
    r"\\(?:section|cvsection|resumesection)\*?\s*\{([^}]+)\}",
    re.IGNORECASE,
)

# Bullet items
_ITEM_RE = re.compile(r"\\item\s+(.*?)(?=\\item|\\end\{|$)", re.DOTALL)

# Contact fields
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"[\+\(]?[\d\s\-\(\)]{7,}")
_URL_RE = re.compile(r"https?://[^\s\}]+|www\.[^\s\}]+")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w-]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"github\.com/[\w-]+", re.IGNORECASE)

# Date ranges
_DATE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"|\d{4}",
    re.IGNORECASE,
)


def _strip_latex_commands(text: str) -> str:
    """Remove LaTeX commands, keep content."""
    text = _COMMENT_RE.sub("", text)
    text = re.sub(r"\\[a-zA-Z]+\*?\s*", " ", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_braced_args(text: str) -> list[str]:
    return _BRACE_CONTENT.findall(text)


def parse_latex_resume(latex_source: str) -> ParsedResume:
    """Parse a LaTeX resume into structured data."""
    result = ParsedResume()
    source = _COMMENT_RE.sub("", latex_source)

    # Extract contact info from preamble / header block
    _extract_contact(source, result)

    # Split into sections
    sections = _split_sections(source)
    result.raw_sections = {k: v for k, v in sections.items()}

    for section_name, section_body in sections.items():
        name_lower = section_name.lower()
        if any(k in name_lower for k in ("experience", "employment", "work")):
            result.experience = _parse_entries(section_body)
        elif any(k in name_lower for k in ("education", "academic")):
            result.education = _parse_entries(section_body)
        elif any(k in name_lower for k in ("project",)):
            result.projects = _parse_entries(section_body)
        elif any(k in name_lower for k in ("skill", "technical", "technology")):
            result.skills = _parse_skills(section_body)
        elif any(k in name_lower for k in ("summary", "objective", "profile")):
            result.summary = _strip_latex_commands(section_body)
        elif any(k in name_lower for k in ("certif", "award", "honor")):
            result.certifications = _parse_flat_list(section_body)

    return result


def _extract_contact(source: str, result: ParsedResume) -> None:
    # Try to find name — usually \name{First}{Last} or \author{Name}
    name_match = re.search(r"\\(?:name|author)\{([^}]+)\}(?:\{([^}]+)\})?", source)
    if name_match:
        parts = [p for p in name_match.groups() if p]
        result.name = " ".join(parts)

    emails = _EMAIL_RE.findall(source)
    if emails:
        result.email = emails[0]

    phones = _PHONE_RE.findall(source[:2000])
    if phones:
        result.phone = phones[0].strip()

    linkedin = _LINKEDIN_RE.search(source)
    if linkedin:
        result.linkedin = "https://" + linkedin.group(0)

    github = _GITHUB_RE.search(source)
    if github:
        result.github = "https://" + github.group(0)


def _split_sections(source: str) -> dict[str, str]:
    """Split LaTeX source into named sections."""
    parts = _SECTION_RE.split(source)
    if len(parts) < 3:
        return {"body": source}
    sections: dict[str, str] = {}
    # parts = [pre, name1, body1, name2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        name = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[name] = body
    return sections


def _parse_entries(section_body: str) -> list[LatexEntry]:
    """Parse cventry / experience items."""
    entries: list[LatexEntry] = []

    # Try moderncv \cventry{dates}{title}{org}{location}{}{bullets}
    cventry_re = re.compile(
        r"\\cventry\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{(.*?)\}",
        re.DOTALL,
    )
    for m in cventry_re.finditer(section_body):
        dates, title, org, loc, _, bullet_block = m.groups()
        dates_found = _DATE_RE.findall(dates)
        entry = LatexEntry(
            title=_strip_latex_commands(title),
            organization=_strip_latex_commands(org),
            location=_strip_latex_commands(loc),
            start_date=dates_found[0] if dates_found else "",
            end_date=dates_found[1] if len(dates_found) > 1 else "Present",
            bullets=_parse_bullets(bullet_block),
            raw=m.group(0),
        )
        entries.append(entry)
        section_body = section_body.replace(m.group(0), "")

    if entries:
        return entries

    # Fallback: look for itemize environments with date patterns above
    env_re = re.compile(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", re.DOTALL)
    surrounding_re = re.compile(r"([^\n]+)\n.*?\\begin\{itemize\}", re.DOTALL)

    for env_match in env_re.finditer(section_body):
        bullets = _parse_bullets(env_match.group(1))
        # Try to find context before the itemize
        pre_text = section_body[: env_match.start()][-300:]
        braced = _extract_braced_args(pre_text)
        entry = LatexEntry(bullets=bullets, raw=env_match.group(0))
        if len(braced) >= 2:
            entry.title = braced[0]
            entry.organization = braced[1] if len(braced) > 1 else ""
        entries.append(entry)

    return entries


def _parse_bullets(bullet_block: str) -> list[LatexBullet]:
    items = []
    for m in _ITEM_RE.finditer(bullet_block):
        raw = m.group(1).strip()
        text = _strip_latex_commands(raw)
        if text:
            items.append(LatexBullet(text=text, raw=raw))
    return items


def _parse_skills(section_body: str) -> list[str]:
    """Extract skills from a skills section."""
    # Remove LaTeX structure, split on common delimiters
    cleaned = _strip_latex_commands(section_body)
    # Split on comma, semicolon, bullet, pipe
    parts = re.split(r"[,;•|/\n]+", cleaned)
    return [p.strip() for p in parts if len(p.strip()) > 1]


def _parse_flat_list(section_body: str) -> list[str]:
    items = []
    for m in _ITEM_RE.finditer(section_body):
        text = _strip_latex_commands(m.group(1))
        if text:
            items.append(text)
    if not items:
        cleaned = _strip_latex_commands(section_body)
        items = [l.strip() for l in cleaned.splitlines() if l.strip()]
    return items
