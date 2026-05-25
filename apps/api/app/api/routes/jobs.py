from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import AnalysisJob, JobStatus, User
from app.db.session import get_db
from app.schemas.job import JobResponse
from worker.jobs import run_rosetta_ddg


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


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.created_by == user.id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="only failed jobs can be retried")
    if job.job_type != "rosetta_ddg":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="retry is not supported for this job type")

    job.status = JobStatus.QUEUED
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    run_rosetta_ddg.delay(job.id)
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.created_by == user.id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only queued or running jobs can be cancelled",
        )

    summary = dict(job.result_summary_json or {})
    summary["message"] = "real data refresh cancellation requested"
    if job.parameters_json and "progress" in job.parameters_json:
        summary["progress"] = job.parameters_json["progress"]
    job.status = JobStatus.CANCELLED
    job.result_summary_json = summary
    db.commit()
    db.refresh(job)
    return job
