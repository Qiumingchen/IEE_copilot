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
from worker.jobs import (
    finish_conservation_profile_job,
    finish_homology_collection_job,
    finish_msa_job,
    finish_placeholder_job,
    mark_job_failed,
)


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
    assert job.result_summary_json["message"] == "homolog collection completed"
    assert job.result_summary_json["homolog_count"] == 2
    assert job.result_summary_json["artifact_type"] == "homolog_sequences"
    assert [homolog["accession"] for homolog in job.result_summary_json["homologs"]] == [
        "MOCK_HOMOLOG_90",
        "MOCK_HOMOLOG_80",
    ]
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/homolog-sequences.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0
    assert artifact.checksum is not None


def test_finish_msa_job_creates_msa_artifact_from_target_sequence():
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
            name="Worker MSA test mTGase",
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
                checksum="worker-msa-test-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme_id,
            job_type="msa",
            status=JobStatus.QUEUED,
            parameters_json={
                "homologs": [
                    {"identifier": "homolog_1", "sequence": "ACDEFGHIVL"},
                    {"identifier": "homolog_2", "sequence": "ACDEYGHIKL"},
                ]
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_msa_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "msa",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json == {
        "message": "MSA completed",
        "sequence_count": 3,
        "alignment_length": 10,
        "artifact_type": "msa",
        "msa_fasta": ">query\nACDEFGHIKL\n>homolog_1\nACDEFGHIVL\n>homolog_2\nACDEYGHIKL\n",
    }
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/msa.fasta"
    assert artifact.content_type == "text/x-fasta"
    assert artifact.size_bytes > 0
    assert artifact.checksum is not None


def test_finish_conservation_profile_job_creates_conservation_artifact():
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
            name="Worker conservation test mTGase",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        enzyme_id = enzyme.id
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACD",
                mature_sequence="ACD",
                source="test",
                checksum="worker-conservation-test-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme_id,
            job_type="conservation_profile",
            status=JobStatus.QUEUED,
            parameters_json={
                "aligned_records": [
                    {"identifier": "query", "aligned_sequence": "ACD"},
                    {"identifier": "homolog_1", "aligned_sequence": "ACD"},
                    {"identifier": "homolog_2", "aligned_sequence": "ACE"},
                    {"identifier": "homolog_3", "aligned_sequence": "A-D"},
                ]
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_conservation_profile_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "conservation_profile",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json == {
        "message": "conservation profile completed",
        "site_count": 3,
        "sequence_count": 4,
        "artifact_type": "conservation_profile",
        "sites": [
            {
                "query_position": 1,
                "alignment_column": 1,
                "wildtype_residue": "A",
                "shannon_entropy": 0.0,
                "wildtype_frequency": 1.0,
                "conservation_category": "highly_conserved",
            },
            {
                "query_position": 2,
                "alignment_column": 2,
                "wildtype_residue": "C",
                "shannon_entropy": 0.811,
                "wildtype_frequency": 0.75,
                "conservation_category": "moderately_conserved",
            },
            {
                "query_position": 3,
                "alignment_column": 3,
                "wildtype_residue": "D",
                "shannon_entropy": 0.811,
                "wildtype_frequency": 0.75,
                "conservation_category": "moderately_conserved",
            },
        ],
    }
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/conservation-profile.json"
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
