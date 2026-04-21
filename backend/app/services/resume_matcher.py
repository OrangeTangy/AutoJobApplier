"""
Resume Library Matcher.

Finds the best-matching resume from the user's library for a given job
description using TF-IDF cosine similarity. No LLM or external API required.

Usage:
    scores = await match_resumes(db, user_id, job_description_text)
    best = scores[0]  # (resume_id, resume_name, score_0_to_100)
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import Resume
from app.utils.latex import parse_latex_resume

logger = structlog.get_logger(__name__)


@dataclass
class ResumeMatch:
    resume_id: uuid.UUID
    resume_name: str
    score: int          # 0-100
    matched_terms: list[str]


async def match_resumes(
    db: AsyncSession,
    user_id: uuid.UUID,
    job_text: str,
    top_k: int = 5,
) -> list[ResumeMatch]:
    """
    Score every base resume in the user's library against the job description.
    Returns up to `top_k` results sorted by descending score.

    Only base resumes (is_base=True) are included — these are the user's
    curated library. Tailored/derived resumes are excluded.
    """
    result = await db.execute(
        select(Resume).where(
            Resume.user_id == user_id,
            Resume.is_base == True,  # noqa: E712
            Resume.deleted_at.is_(None),
        )
    )
    resumes = result.scalars().all()

    if not resumes:
        logger.warning("no_library_resumes", user_id=str(user_id))
        return []

    # Extract plain text from each LaTeX resume
    resume_texts: list[tuple[Resume, str]] = []
    for r in resumes:
        if not r.latex_source:
            continue
        try:
            parsed = parse_latex_resume(r.latex_source)
            text = _resume_to_searchable_text(parsed, r.latex_source)
            resume_texts.append((r, text))
        except Exception as exc:
            logger.warning("resume_parse_failed", resume_id=str(r.id), error=str(exc))

    if not resume_texts:
        return []

    # Build corpus: [job_text, resume1, resume2, ...]
    corpus = [_clean_text(job_text)] + [_clean_text(t) for _, t in resume_texts]

    # TF-IDF vectorisation with tech-aware tokenisation
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        max_features=5000,
        sublinear_tf=True,
        strip_accents="unicode",
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#.\-]{1,}\b",
    )
    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        # Corpus is empty after preprocessing
        return []

    job_vec = tfidf_matrix[0]
    resume_vecs = tfidf_matrix[1:]

    similarities = cosine_similarity(job_vec, resume_vecs)[0]

    # Build result list with matched key terms
    feature_names = vectorizer.get_feature_names_out()
    job_feature_indices = job_vec.nonzero()[1]
    job_terms = {feature_names[i] for i in job_feature_indices}

    matches: list[ResumeMatch] = []
    for idx, (resume, _) in enumerate(resume_texts):
        raw_score = float(similarities[idx])
        score_0_100 = min(100, round(raw_score * 200))  # scale: 0.5 cosine → 100

        # Find overlapping terms between job and this resume
        resume_vec = resume_vecs[idx]
        resume_feature_indices = resume_vec.nonzero()[1]
        resume_terms = {feature_names[i] for i in resume_feature_indices}
        matched = sorted(job_terms & resume_terms, key=lambda t: len(t), reverse=True)[:10]

        matches.append(ResumeMatch(
            resume_id=resume.id,
            resume_name=resume.name,
            score=score_0_100,
            matched_terms=list(matched),
        ))

    matches.sort(key=lambda m: m.score, reverse=True)
    logger.info(
        "resume_match_complete",
        user_id=str(user_id),
        library_size=len(matches),
        top_score=matches[0].score if matches else 0,
        top_resume=matches[0].resume_name if matches else "none",
    )
    return matches[:top_k]


async def get_best_resume(
    db: AsyncSession,
    user_id: uuid.UUID,
    job_text: str,
) -> tuple[Resume | None, int, list[str]]:
    """
    Convenience wrapper — returns (best_resume_object, score, matched_terms).
    Returns (None, 0, []) if no library resumes exist.
    """
    matches = await match_resumes(db, user_id, job_text, top_k=1)
    if not matches:
        return None, 0, []

    best = matches[0]
    resume = await db.get(Resume, best.resume_id)
    return resume, best.score, best.matched_terms


# ── Text helpers ──────────────────────────────────────────────────────────────

def _resume_to_searchable_text(parsed, raw_latex: str) -> str:
    """Combine parsed resume fields into a single searchable string."""
    parts: list[str] = []

    if parsed.name:
        parts.append(parsed.name)

    # Skills section
    for skill_line in parsed.skills:
        parts.append(skill_line)

    # Experience bullets
    for exp in parsed.experience:
        if exp.get("title"):
            parts.append(exp["title"])
        if exp.get("company"):
            parts.append(exp["company"])
        for bullet in exp.get("bullets", []):
            parts.append(bullet)

    # Education
    for edu in parsed.education:
        parts.append(f"{edu.get('degree','')} {edu.get('field','')} {edu.get('institution','')}")

    # Also include raw LaTeX stripped of markup to catch any missed content
    stripped = re.sub(r"\\[a-zA-Z]+(\[.*?\])?\{([^}]*)\}", r"\2", raw_latex)
    stripped = re.sub(r"[{}\\%]", " ", stripped)
    parts.append(stripped[:3000])

    return " ".join(parts)


def _clean_text(text: str) -> str:
    """Normalise whitespace and lowercase."""
    text = re.sub(r"[^\w\s.#+\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text
