from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisArtifact, AnalysisJob, JobStatus
from app.db.session import SessionLocal
from app.tasks.celery_app import celery_app


def finish_placeholder_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")

    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    artifact = AnalysisArtifact(
        project_id=job.project_id,
        enzyme_entry_id=job.enzyme_entry_id,
        job_id=job.id,
        artifact_type="family_profile_summary",
        bucket=bucket,
        object_key=f"analysis-jobs/{job.id}/family-profile-summary.json",
        content_type="application/json",
        size_bytes=0,
    )
    db.add(artifact)

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {"message": "placeholder analysis completed"}
    db.commit()
    db.refresh(job)
    return job


def mark_job_failed(db: Session, job_id: str, error_message: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")

    job.status = JobStatus.FAILED
    job.error_message = error_message
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


@celery_app.task(bind=True, name="worker.jobs.run_placeholder_analysis")
def run_placeholder_analysis(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_placeholder_job(db, job_id, bucket=get_settings().minio_bucket)
            return job.id
    except Exception as exc:
        with SessionLocal() as db:
            mark_job_failed(db, job_id, str(exc))
        raise
