from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import AnalysisJob, User
from app.db.session import get_db
from app.schemas.job import JobResponse


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisJob]:
    return list(
        db.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.created_by == user.id)
            .order_by(AnalysisJob.created_at.desc())
        )
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.created_by == user.id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job
