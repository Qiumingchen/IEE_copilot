import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisArtifact, AnalysisJob, JobStatus, ProteinSequence
from app.db.session import SessionLocal
from app.services.conservation import calculate_conservation_profile
from app.services.homology import HomologSearchParameters, HomologSequence, collect_homologs
from app.services.msa import MsaAlignedRecord, MsaAlignment, MsaInputSequence, run_mock_mafft
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


def finish_homology_collection_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    if job.enzyme_entry_id is None:
        raise ValueError(f"analysis job has no enzyme entry: {job_id}")

    protein_sequence = db.scalar(
        select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == job.enzyme_entry_id)
    )
    if protein_sequence is None:
        raise ValueError(f"protein sequence not found for enzyme entry: {job.enzyme_entry_id}")

    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    query_sequence = protein_sequence.mature_sequence or protein_sequence.sequence
    parameters = _homolog_parameters_from_job(job)
    homologs = collect_homologs(
        query_sequence,
        _mock_homolog_candidates(query_sequence),
        parameters=parameters,
    )
    payload = {
        "query_sequence_length": len(query_sequence),
        "parameters": {
            "identity_min": parameters.identity_min,
            "identity_max": parameters.identity_max,
            "coverage_min": parameters.coverage_min,
            "max_sequences": parameters.max_sequences,
        },
        "homologs": [
            {
                "accession": homolog.accession,
                "name": homolog.name,
                "organism": homolog.organism,
                "sequence": homolog.sequence,
                "source": homolog.source,
                "identity": homolog.identity,
                "coverage": homolog.coverage,
            }
            for homolog in homologs
        ],
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    db.add(
        AnalysisArtifact(
            project_id=job.project_id,
            enzyme_entry_id=job.enzyme_entry_id,
            job_id=job.id,
            artifact_type="homolog_sequences",
            bucket=bucket,
            object_key=f"analysis-jobs/{job.id}/homolog-sequences.json",
            checksum=hashlib.sha256(payload_bytes).hexdigest(),
            content_type="application/json",
            size_bytes=len(payload_bytes),
        )
    )

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {
        "message": "homolog collection completed",
        "homolog_count": len(homologs),
        "artifact_type": "homolog_sequences",
    }
    db.commit()
    db.refresh(job)
    return job


def finish_msa_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    if job.enzyme_entry_id is None:
        raise ValueError(f"analysis job has no enzyme entry: {job_id}")

    protein_sequence = db.scalar(
        select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == job.enzyme_entry_id)
    )
    if protein_sequence is None:
        raise ValueError(f"protein sequence not found for enzyme entry: {job.enzyme_entry_id}")

    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    query_sequence = protein_sequence.mature_sequence or protein_sequence.sequence
    alignment = run_mock_mafft(
        [
            MsaInputSequence(identifier="query", sequence=query_sequence),
            *_homolog_inputs_from_job(job),
        ]
    )
    payload_bytes = alignment.to_fasta().encode("utf-8")

    db.add(
        AnalysisArtifact(
            project_id=job.project_id,
            enzyme_entry_id=job.enzyme_entry_id,
            job_id=job.id,
            artifact_type="msa",
            bucket=bucket,
            object_key=f"analysis-jobs/{job.id}/msa.fasta",
            checksum=hashlib.sha256(payload_bytes).hexdigest(),
            content_type="text/x-fasta",
            size_bytes=len(payload_bytes),
        )
    )

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {
        "message": "MSA completed",
        "sequence_count": alignment.sequence_count,
        "alignment_length": alignment.alignment_length,
        "artifact_type": "msa",
    }
    db.commit()
    db.refresh(job)
    return job


def finish_conservation_profile_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    if job.enzyme_entry_id is None:
        raise ValueError(f"analysis job has no enzyme entry: {job_id}")

    alignment = _alignment_from_job(job)
    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    profile = calculate_conservation_profile(alignment, query_identifier="query")
    payload = {
        "sequence_count": profile.sequence_count,
        "sites": [
            {
                "query_position": site.query_position,
                "alignment_column": site.alignment_column,
                "wildtype_residue": site.wildtype_residue,
                "shannon_entropy": site.shannon_entropy,
                "wildtype_frequency": site.wildtype_frequency,
                "conservation_category": site.conservation_category,
            }
            for site in profile.sites
        ],
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    db.add(
        AnalysisArtifact(
            project_id=job.project_id,
            enzyme_entry_id=job.enzyme_entry_id,
            job_id=job.id,
            artifact_type="conservation_profile",
            bucket=bucket,
            object_key=f"analysis-jobs/{job.id}/conservation-profile.json",
            checksum=hashlib.sha256(payload_bytes).hexdigest(),
            content_type="application/json",
            size_bytes=len(payload_bytes),
        )
    )

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {
        "message": "conservation profile completed",
        "site_count": len(profile.sites),
        "sequence_count": profile.sequence_count,
        "artifact_type": "conservation_profile",
    }
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


@celery_app.task(bind=True, name="worker.jobs.run_homology_collection")
def run_homology_collection(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_homology_collection_job(db, job_id, bucket=get_settings().minio_bucket)
            return job.id
    except Exception as exc:
        with SessionLocal() as db:
            mark_job_failed(db, job_id, str(exc))
        raise


@celery_app.task(bind=True, name="worker.jobs.run_msa")
def run_msa(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_msa_job(db, job_id, bucket=get_settings().minio_bucket)
            return job.id
    except Exception as exc:
        with SessionLocal() as db:
            mark_job_failed(db, job_id, str(exc))
        raise


@celery_app.task(bind=True, name="worker.jobs.run_conservation_profile")
def run_conservation_profile(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_conservation_profile_job(db, job_id, bucket=get_settings().minio_bucket)
            return job.id
    except Exception as exc:
        with SessionLocal() as db:
            mark_job_failed(db, job_id, str(exc))
        raise


def _homolog_parameters_from_job(job: AnalysisJob) -> HomologSearchParameters:
    raw = job.parameters_json or {}
    return HomologSearchParameters(
        identity_min=raw.get("identity_min", 40),
        identity_max=raw.get("identity_max", 95),
        coverage_min=raw.get("coverage_min", 70),
        max_sequences=raw.get("max_sequences", 500),
    )


def _mock_homolog_candidates(query_sequence: str) -> list[HomologSequence]:
    return [
        HomologSequence(
            accession="MOCK_EXACT",
            name="Mock exact self hit",
            organism="Synthetic construct",
            sequence=query_sequence,
            source="homology_mock",
        ),
        HomologSequence(
            accession="MOCK_HOMOLOG_90",
            name="Mock accepted homolog 90",
            organism="Streptomyces homologensis",
            sequence=_mutate_every_nth_residue(query_sequence, 10),
            source="homology_mock",
        ),
        HomologSequence(
            accession="MOCK_HOMOLOG_80",
            name="Mock accepted homolog 80",
            organism="Streptomyces variantensis",
            sequence=_mutate_every_nth_residue(query_sequence, 5),
            source="homology_mock",
        ),
        HomologSequence(
            accession="MOCK_LOW_COVERAGE",
            name="Mock low coverage fragment",
            organism="Fragment organism",
            sequence=query_sequence[: max(1, len(query_sequence) // 2)],
            source="homology_mock",
        ),
        HomologSequence(
            accession="MOCK_LOW_IDENTITY",
            name="Mock low identity sequence",
            organism="Distant organism",
            sequence="V" * len(query_sequence),
            source="homology_mock",
        ),
    ]


def _mutate_every_nth_residue(sequence: str, step: int) -> str:
    residues = list(sequence)
    for index in range(step - 1, len(residues), step):
        residues[index] = "V" if residues[index].upper() != "V" else "A"
    return "".join(residues)


def _homolog_inputs_from_job(job: AnalysisJob) -> list[MsaInputSequence]:
    raw = job.parameters_json or {}
    homologs = raw.get("homologs", [])
    return [
        MsaInputSequence(
            identifier=str(homolog.get("identifier") or homolog.get("accession") or f"homolog_{index + 1}"),
            sequence=str(homolog["sequence"]),
        )
        for index, homolog in enumerate(homologs)
        if homolog.get("sequence")
    ]


def _alignment_from_job(job: AnalysisJob) -> MsaAlignment:
    raw = job.parameters_json or {}
    records = raw.get("aligned_records", [])
    return MsaAlignment(
        records=[
            MsaAlignedRecord(
                identifier=str(record["identifier"]),
                aligned_sequence=str(record["aligned_sequence"]),
            )
            for record in records
            if record.get("identifier") and record.get("aligned_sequence")
        ]
    )
