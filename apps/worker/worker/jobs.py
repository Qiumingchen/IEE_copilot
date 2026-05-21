import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisArtifact, AnalysisJob, EnzymeEntry, EnzymeFamily, JobStatus, ProteinSequence
from app.db.session import SessionLocal
from app.external.uniprot import get_uniprot_client
from app.services.conservation import calculate_conservation_profile
from app.services.homology import (
    HomologSearchParameters,
    HomologSequence,
    collect_homologs,
    fetch_uniprot_homolog_candidates,
)
from app.services.library_design import design_mutation_library
from app.services.mutation_scoring import MutationScore, calculate_general_score, calculate_module_specific_score
from app.services.mutations import (
    generate_rosetta_mutation_file,
    normalize_mutation_string,
    parse_mutation_string,
)
from app.services.mutation_recommendation import recommend_mutation_hotspots
from app.services.msa import MsaAlignedRecord, MsaAlignment, MsaInputSequence
from app.services.msa_runner import run_msa_with_runner
from app.services.provenance import build_fallback_provenance, build_real_provenance
from app.services.residue_features import build_residue_feature_records
from app.services.rosetta_runner import run_rosetta_ddg_with_runner
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

    enzyme = db.get(EnzymeEntry, job.enzyme_entry_id)
    if enzyme is None:
        raise ValueError(f"enzyme entry not found: {job.enzyme_entry_id}")

    query_sequence = protein_sequence.mature_sequence or protein_sequence.sequence
    parameters = _homolog_parameters_from_job(job)
    settings = get_settings()
    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence=query_sequence,
        max_sequences=parameters.max_sequences,
        provider_fetch_size=settings.homolog_provider_fetch_size,
        use_real_provider=settings.use_real_science_providers,
        allow_fallback=settings.allow_science_fallbacks,
    )
    homologs = collect_homologs(
        query_sequence,
        candidates,
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
        "runner": runner,
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
        "homologs": payload["homologs"],
        "runner": runner,
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
    settings = get_settings()
    msa_result = run_msa_with_runner(
        [
            MsaInputSequence(identifier="query", sequence=query_sequence),
            *_homolog_inputs_from_job(job),
        ],
        mafft_bin=settings.mafft_bin,
        allow_fallback=settings.allow_science_fallbacks,
    )
    alignment = msa_result.alignment
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
        "msa_fasta": alignment.to_fasta(),
        "runner": msa_result.runner,
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
        "sites": [
            {
                "query_position": site.query_position,
                "alignment_column": site.alignment_column,
                "wildtype_residue": site.wildtype_residue,
                "shannon_entropy": round(site.shannon_entropy, 3),
                "wildtype_frequency": round(site.wildtype_frequency, 3),
                "conservation_category": site.conservation_category,
            }
            for site in profile.sites
        ],
    }
    db.commit()
    db.refresh(job)
    return job


def finish_mutation_recommendation_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    if job.enzyme_entry_id is None:
        raise ValueError(f"analysis job has no enzyme entry: {job_id}")

    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    parameters = job.parameters_json or {}
    raw_sites = parameters.get("conservation_sites", [])
    conservation_sites = [site for site in raw_sites if isinstance(site, dict)] if isinstance(raw_sites, list) else []
    candidates = recommend_mutation_hotspots(conservation_sites)
    protein_sequence = db.scalar(
        select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == job.enzyme_entry_id)
    )
    if protein_sequence is not None:
        sequence = protein_sequence.mature_sequence or protein_sequence.sequence
        module = _enzyme_module(db, job.enzyme_entry_id)
        candidates = _score_recommendation_candidates(
            candidates,
            sequence=sequence,
            module=module,
            conservation_sites=conservation_sites,
            structure_summaries=_list_of_dicts(parameters.get("structure_summaries")),
            mutation_records=_list_of_dicts(parameters.get("mutation_records")),
            rosetta_results=_list_of_dicts(parameters.get("rosetta_results")),
        )
    payload = {
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    db.add(
        AnalysisArtifact(
            project_id=job.project_id,
            enzyme_entry_id=job.enzyme_entry_id,
            job_id=job.id,
            artifact_type="mutation_recommendations",
            bucket=bucket,
            object_key=f"analysis-jobs/{job.id}/mutation-recommendations.json",
            checksum=hashlib.sha256(payload_bytes).hexdigest(),
            content_type="application/json",
            size_bytes=len(payload_bytes),
        )
    )

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {
        "message": "mutation recommendation completed",
        "candidate_count": len(candidates),
        "artifact_type": "mutation_recommendations",
        "candidates": candidates,
    }
    db.commit()
    db.refresh(job)
    return job


def _score_recommendation_candidates(
    candidates: list[dict],
    *,
    sequence: str,
    module,
    conservation_sites: list[dict],
    structure_summaries: list[dict],
    mutation_records: list[dict],
    rosetta_results: list[dict],
) -> list[dict]:
    residue_features = build_residue_feature_records(
        sequence,
        conservation_sites=conservation_sites,
        structure_summaries=structure_summaries,
        mutation_records=mutation_records,
        rosetta_results=rosetta_results,
    )
    scored_candidates = []
    for candidate in candidates:
        scored_suggestions = [
            _mutation_score_response(_calculate_recommendation_score(str(mutation_string), residue_features, module))
            for mutation_string in candidate.get("suggested_mutations", [])
            if mutation_string
        ]
        scored_candidates.append(
            {
                **candidate,
                "scored_suggestions": sorted(
                    scored_suggestions,
                    key=lambda suggestion: suggestion["total_score"],
                    reverse=True,
                ),
            }
        )
    return scored_candidates


def _calculate_recommendation_score(
    mutation_string: str,
    residue_features: list,
    module,
) -> MutationScore:
    if module is None:
        return calculate_general_score(mutation_string, residue_features)
    return calculate_module_specific_score(mutation_string, residue_features, module)


def _mutation_score_response(score: MutationScore) -> dict:
    return {
        "mutation_string": score.mutation_string,
        "total_score": score.total_score,
        "components": [
            {
                "name": component.name,
                "value": component.value,
                "weight": component.weight,
                "contribution": component.contribution,
                "rationale": component.rationale,
            }
            for component in score.components
        ],
        "risk_summary": score.risk_summary,
        "parsed_mutations": score.parsed_mutations,
    }


def _list_of_dicts(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _homolog_candidates_for_job(
    enzyme: EnzymeEntry,
    *,
    query_sequence: str,
    max_sequences: int,
    provider_fetch_size: int,
    use_real_provider: bool,
    allow_fallback: bool,
) -> tuple[list[HomologSequence], dict]:
    if use_real_provider:
        requested_size = max(1, min(max_sequences, provider_fetch_size))
        try:
            candidates = fetch_uniprot_homolog_candidates(
                enzyme_name=enzyme.name,
                ec_number=enzyme.ec_number,
                uniprot_client=get_uniprot_client(),
                size=requested_size,
            )
            if candidates:
                return candidates, build_real_provenance(
                    provider="uniprot",
                    extra={"candidate_count": len(candidates), "requested_size": requested_size},
                )
            if not allow_fallback:
                raise RuntimeError("UniProt homolog collection returned no candidates")
            return _mock_homolog_candidates(query_sequence), build_fallback_provenance(
                provider="uniprot",
                warning="UniProt homolog collection returned no candidates; mock homolog candidates used.",
                extra={"requested_size": requested_size},
            )
        except Exception as exc:
            if not allow_fallback:
                raise RuntimeError(f"UniProt homolog collection failed: {exc}") from exc
            return _mock_homolog_candidates(query_sequence), build_fallback_provenance(
                provider="uniprot",
                warning=f"UniProt homolog collection failed; mock homolog candidates used: {exc}",
            )

    if not allow_fallback:
        raise RuntimeError("UniProt homolog collection is unavailable and science fallbacks are disabled")

    return _mock_homolog_candidates(query_sequence), build_fallback_provenance(
        provider="uniprot",
        warning="Real UniProt homolog collection disabled; mock homolog candidates used.",
    )


def _enzyme_module(db: Session, enzyme_id: str):
    row = db.execute(
        select(EnzymeFamily.module)
        .join(EnzymeEntry, EnzymeEntry.family_id == EnzymeFamily.id)
        .where(EnzymeEntry.id == enzyme_id)
    ).first()
    return row[0] if row is not None else None


def finish_rosetta_ddg_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    if job.enzyme_entry_id is None:
        raise ValueError(f"analysis job has no enzyme entry: {job_id}")

    parameters = job.parameters_json or {}
    mutation_string = str(parameters.get("mutation_string") or "").strip()
    if not mutation_string:
        raise ValueError("mutation_string is required for Rosetta ddG job")
    mutations = parse_mutation_string(mutation_string)
    normalized_mutation_string = normalize_mutation_string(mutations)
    mutation_file = generate_rosetta_mutation_file(mutations)

    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    settings = get_settings()
    rosetta_result = run_rosetta_ddg_with_runner(
        mutation_string=normalized_mutation_string,
        mutations=mutations,
        mutation_file=mutation_file,
        command=settings.rosetta_ddg_command or settings.rosetta_ddg_bin,
        allow_fallback=settings.allow_science_fallbacks,
    )
    payload = {
        "structure_id": parameters.get("structure_id"),
        **rosetta_result.payload,
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    db.add(
        AnalysisArtifact(
            project_id=job.project_id,
            enzyme_entry_id=job.enzyme_entry_id,
            job_id=job.id,
            artifact_type="rosetta_ddg",
            bucket=bucket,
            object_key=f"analysis-jobs/{job.id}/rosetta-ddg.json",
            checksum=hashlib.sha256(payload_bytes).hexdigest(),
            content_type="application/json",
            size_bytes=len(payload_bytes),
        )
    )

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {
        "message": "Rosetta ddG completed",
        "artifact_type": "rosetta_ddg",
        **payload,
    }
    db.commit()
    db.refresh(job)
    return job


def finish_library_design_job(db: Session, job_id: str, bucket: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    if job.enzyme_entry_id is None:
        raise ValueError(f"analysis job has no enzyme entry: {job_id}")

    parameters = job.parameters_json or {}
    recommendation_candidates = parameters.get("recommendation_candidates", [])
    rosetta_results = parameters.get("rosetta_results", [])

    now = datetime.utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    db.commit()

    payload = design_mutation_library(
        recommendation_candidates=[
            candidate for candidate in recommendation_candidates if isinstance(candidate, dict)
        ]
        if isinstance(recommendation_candidates, list)
        else [],
        rosetta_results=[result for result in rosetta_results if isinstance(result, dict)]
        if isinstance(rosetta_results, list)
        else [],
        library_size=int(parameters.get("library_size") or 24),
        max_order=int(parameters.get("max_order") or 2),
        plate_format=int(parameters.get("plate_format") or 96),
    )
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    db.add(
        AnalysisArtifact(
            project_id=job.project_id,
            enzyme_entry_id=job.enzyme_entry_id,
            job_id=job.id,
            artifact_type="mutation_library",
            bucket=bucket,
            object_key=f"analysis-jobs/{job.id}/mutation-library.json",
            checksum=hashlib.sha256(payload_bytes).hexdigest(),
            content_type="application/json",
            size_bytes=len(payload_bytes),
        )
    )

    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {
        "message": "mutation library design completed",
        "artifact_type": "mutation_library",
        **payload,
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


@celery_app.task(bind=True, name="worker.jobs.run_mutation_recommendation")
def run_mutation_recommendation(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_mutation_recommendation_job(db, job_id, bucket=get_settings().minio_bucket)
            return job.id
    except Exception as exc:
        with SessionLocal() as db:
            mark_job_failed(db, job_id, str(exc))
        raise


@celery_app.task(bind=True, name="worker.jobs.run_rosetta_ddg")
def run_rosetta_ddg(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_rosetta_ddg_job(db, job_id, bucket=get_settings().minio_bucket)
            return job.id
    except Exception as exc:
        with SessionLocal() as db:
            mark_job_failed(db, job_id, str(exc))
        raise


@celery_app.task(bind=True, name="worker.jobs.run_library_design")
def run_library_design(_task, job_id: str) -> str:
    try:
        with SessionLocal() as db:
            job = finish_library_design_job(db, job_id, bucket=get_settings().minio_bucket)
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


def _mock_ddg_for_mutation(mutation_string: str) -> float:
    return round(((sum(ord(char) for char in mutation_string) % 21) - 10) / 5, 2)


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
