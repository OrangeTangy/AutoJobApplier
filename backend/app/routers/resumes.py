from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resume import Resume
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.resume import ResumeCreate, ResumeOut, ResumeTailorRequest
from app.utils.audit import write_audit
from app.utils.encryption import decrypt, encrypt
from app.utils.latex import parse_latex_resume

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    body: ResumeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Resume:
    parsed = parse_latex_resume(body.latex_source)

    # Count words in parsed text
    all_text = " ".join(
        b.text
        for section in [parsed.experience, parsed.projects]
        for entry in section
        for b in entry.bullets
    )
    word_count = len(all_text.split())

    resume = Resume(
        user_id=current_user.id,
        name=body.name,
        is_base=body.is_base,
        latex_source=encrypt(body.latex_source),
        parsed_data=parsed.to_dict(),
        template_name=body.template_name,
        word_count=word_count,
    )
    db.add(resume)
    await db.flush()

    await write_audit(
        db,
        action="resume_uploaded",
        actor="user",
        user_id=current_user.id,
        resource_type="resume",
        resource_id=resume.id,
        metadata={"name": body.name, "is_base": body.is_base},
    )
    return resume


@router.get("", response_model=list[ResumeOut])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Resume]:
    result = await db.execute(
        select(Resume).where(
            Resume.user_id == current_user.id, Resume.deleted_at.is_(None)
        ).order_by(Resume.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Resume:
    return await _get_resume_or_404(resume_id, current_user.id, db)


@router.get("/{resume_id}/latex")
async def get_resume_latex(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    resume = await _get_resume_or_404(resume_id, current_user.id, db)
    return {"latex_source": decrypt(resume.latex_source)}


@router.get("/{resume_id}/pdf")
async def download_resume_pdf(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    resume = await _get_resume_or_404(resume_id, current_user.id, db)
    if not resume.compiled_pdf_path:
        raise HTTPException(status_code=404, detail="PDF not yet compiled")
    return FileResponse(resume.compiled_pdf_path, media_type="application/pdf")


@router.post("/tailor", response_model=ResumeOut, status_code=status.HTTP_202_ACCEPTED)
async def tailor_resume(
    body: ResumeTailorRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Resume:
    """Start async resume tailoring for a specific job."""
    base = await _get_resume_or_404(body.base_resume_id, current_user.id, db)

    tailored = Resume(
        user_id=current_user.id,
        name=f"{base.name} (tailored)",
        is_base=False,
        latex_source=base.latex_source,    # will be replaced async
        base_resume_id=base.id,
        job_id=body.job_id,
    )
    db.add(tailored)
    await db.flush()

    background_tasks.add_task(
        _run_tailoring_async,
        tailored.id,
        body.base_resume_id,
        body.job_id,
        str(current_user.id),
    )
    return tailored


async def _run_tailoring_async(
    tailored_resume_id: uuid.UUID,
    base_resume_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: str,
) -> None:
    from pathlib import Path

    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from app.models.job import Job
    from app.services.resume_tailor import compile_latex_to_pdf, tailor_resume

    settings = get_settings()

    async with AsyncSessionLocal() as db:
        base = await db.get(Resume, base_resume_id)
        tailored = await db.get(Resume, tailored_resume_id)
        job = await db.get(Job, job_id)

        if not all([base, tailored, job]):
            return

        latex_source = decrypt(base.latex_source)
        job_data = {
            "title": job.title,
            "company": job.company,
            "description": job.description,
            "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills,
        }

        result = await tailor_resume(latex_source, job_data, user_id)

        tailored.latex_source = encrypt(result.tailored_latex)
        tailored.tailoring_diff = {
            "edits": [e.model_dump() for e in result.edits],
            "sections_reordered": result.sections_reordered,
            "rationale_summary": result.rationale_summary,
        }
        tailored.parsed_data = parse_latex_resume(result.tailored_latex).to_dict()

        # Compile PDF
        output_dir = Path(settings.local_storage_path) / "resumes" / user_id
        pdf_path = await compile_latex_to_pdf(result.tailored_latex, output_dir)
        if pdf_path:
            tailored.compiled_pdf_path = str(pdf_path)

        await db.commit()


async def _get_resume_or_404(
    resume_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> Resume:
    result = await db.execute(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == user_id,
            Resume.deleted_at.is_(None),
        )
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume
