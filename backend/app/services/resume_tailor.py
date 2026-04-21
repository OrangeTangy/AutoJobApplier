"""
Resume tailoring service.

Takes a base LaTeX resume and a parsed job, produces a tailored LaTeX variant
with only truthful edits — no fabrication of skills, dates, or experience.
Every changed bullet is accompanied by a rationale.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

import aiofiles
import structlog
from pydantic import BaseModel, Field

from app.config import get_settings
from app.utils.latex import ParsedResume, parse_latex_resume

logger = structlog.get_logger(__name__)
settings = get_settings()


# ── Schema ────────────────────────────────────────────────────────────────────

class BulletEdit(BaseModel):
    section: str
    original: str
    tailored: str
    rationale: str


class TailoringResult(BaseModel):
    tailored_latex: str
    edits: list[BulletEdit] = Field(default_factory=list)
    sections_reordered: list[str] = Field(default_factory=list)
    rationale_summary: str = ""


class LLMTailoringOutput(BaseModel):
    edits: list[BulletEdit] = Field(default_factory=list)
    sections_reordered: list[str] = Field(default_factory=list)
    rationale_summary: str = ""


_TAILOR_SYSTEM = """You are a resume tailoring expert. Your ONLY job is to:
1. Reorder or emphasize existing bullet points to highlight relevance to the job
2. Rephrase existing bullets to use job-posting keywords — without changing meaning
3. Suggest reordering sections if it improves relevance

You MUST NOT:
- Add skills, experiences, projects, or qualifications the candidate does not have
- Change dates, companies, titles, GPAs, or any factual information
- Remove bullet points that are truthful
- Invent anything

For each edit, provide the original text, the tailored text, and a clear rationale
explaining WHY this edit improves relevance (cite the specific job requirement it maps to)."""


def _build_tailor_prompt(parsed_resume: ParsedResume, job_data: dict) -> str:
    return f"""Tailor this resume for the job below.

<resume_structured>
Name: {parsed_resume.name}
Experience:
{_format_experience(parsed_resume.experience)}

Projects:
{_format_experience(parsed_resume.projects)}

Skills: {', '.join(parsed_resume.skills[:40])}
</resume_structured>

<job>
Title: {job_data.get('title', '')}
Company: {job_data.get('company', '')}
Required Skills: {job_data.get('required_skills', [])}
Preferred Skills: {job_data.get('preferred_skills', [])}
Description (excerpt): {str(job_data.get('description', ''))[:2000]}
</job>

Return JSON with:
- edits: list of {{section, original, tailored, rationale}}
- sections_reordered: list of section names in recommended order
- rationale_summary: 2-3 sentence overview of tailoring strategy

Only include edits that genuinely improve relevance. Fewer strong edits > many weak ones."""


def _format_experience(entries: list) -> str:
    lines = []
    for e in entries:
        lines.append(f"  [{e.title} @ {e.organization} ({e.start_date}–{e.end_date})]")
        for b in e.bullets:
            lines.append(f"    • {b.text}")
    return "\n".join(lines) or "  (none)"


def _apply_edits(latex_source: str, edits: list[BulletEdit]) -> str:
    """Apply bullet edits to the LaTeX source using string replacement."""
    result = latex_source
    applied = 0
    for edit in edits:
        if edit.original in result:
            result = result.replace(edit.original, edit.tailored, 1)
            applied += 1
        else:
            # Try a relaxed match on the core text
            core = re.escape(edit.original[:60])
            if re.search(core, result):
                result = re.sub(core + r"[^\\]*", edit.tailored, result, count=1)
                applied += 1
    logger.info("resume_edits_applied", applied=applied, total=len(edits))
    return result


async def compile_latex_to_pdf(latex_source: str, output_dir: Path) -> Path | None:
    """Compile LaTeX to PDF in a temp directory. Returns PDF path or None if compilation fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "resume.tex"
        tex_path.write_text(latex_source, encoding="utf-8")
        try:
            proc = await asyncio.create_subprocess_exec(
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory", tmpdir,
                str(tex_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode != 0:
                logger.warning(
                    "pdflatex_failed",
                    stdout=stdout.decode()[-500:],
                    stderr=stderr.decode()[-500:],
                )
                return None

            pdf_src = Path(tmpdir) / "resume.pdf"
            if not pdf_src.exists():
                return None

            output_dir.mkdir(parents=True, exist_ok=True)
            pdf_dest = output_dir / f"{uuid.uuid4()}.pdf"
            async with aiofiles.open(pdf_src, "rb") as src, aiofiles.open(pdf_dest, "wb") as dst:
                await dst.write(await src.read())
            return pdf_dest

        except asyncio.TimeoutError:
            logger.error("pdflatex_timeout")
            return None
        except FileNotFoundError:
            logger.warning("pdflatex_not_installed")
            return None


async def tailor_resume(
    latex_source: str,
    job_data: dict,
    user_id: str,
) -> TailoringResult:
    """
    Resume tailoring — currently returns the source unchanged.

    In the library-matching model the best pre-made resume is selected
    automatically, so no per-job tailoring is applied. This function is
    retained for future use (e.g. if an LLM key is configured).
    """
    logger.info("tailor_resume_passthrough", user_id=user_id)
    return TailoringResult(
        tailored_latex=latex_source,
        edits=[],
        sections_reordered=[],
        rationale_summary="No tailoring applied — library resume used as-is.",
    )
