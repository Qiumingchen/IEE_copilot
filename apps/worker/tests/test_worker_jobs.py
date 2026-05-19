from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    AnalysisArtifact,
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    JobStatus,
    ProteinSequence,
)
from worker.jobs import finish_homology_collection_job, finish_placeholder_job, mark_job_failed


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


def test_finish_homology_collection_job_creates_homolog_sequence_artifact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker test mTGase",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        enzyme_id = enzyme.id
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACDEFGHIKL",
                mature_sequence="ACDEFGHIKL",
                source="test",
                checksum="worker-test-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme_id,
            job_type="homolog_collection",
            status=JobStatus.QUEUED,
            parameters_json={"identity_min": 40, "identity_max": 95, "coverage_min": 70},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_homology_collection_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "homolog_sequences",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json == {
        "message": "homolog collection completed",
        "homolog_count": 2,
        "artifact_type": "homolog_sequences",
    }
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/homolog-sequences.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0
    assert artifact.checksum is not None


def test_mark_job_failed_records_error_message():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        job = AnalysisJob(job_type="family_profile_placeholder", status=JobStatus.RUNNING)
        db.add(job)
        db.commit()
        db.refresh(job)

        mark_job_failed(db, job.id, "Rosetta executable missing")

        db.refresh(job)

    assert job.status == JobStatus.FAILED
    assert job.error_message == "Rosetta executable missing"
    assert job.finished_at is not None
