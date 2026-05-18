from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import AnalysisArtifact, AnalysisJob, JobStatus
from worker.jobs import finish_placeholder_job


def test_finish_placeholder_job_marks_job_finished_and_creates_artifact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        job = AnalysisJob(job_type="family_profile_placeholder", status=JobStatus.QUEUED)
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_placeholder_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.job_id == job.id))

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json == {"message": "placeholder analysis completed"}
    assert artifact is not None
    assert artifact.artifact_type == "family_profile_summary"
