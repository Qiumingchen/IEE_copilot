import base64

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    AnalysisArtifact,
    AnalysisJob,
    CurationStatus,
    EnzymeEntry,
    ExperimentCondition,
    ExpressionRecord,
    KineticRecord,
    LigandEntry,
    JobStatus,
    MutationRecord,
    PropertyRecord,
    ProteinSequence,
    Project,
    StructureEntry,
    SubstrateEntry,
    User,
    UserExperiment,
    Visibility,
)
from app.db.session import get_db
from app.schemas.enzyme_record import (
    AnalysisArtifactContentResponse,
    AnalysisArtifactResponse,
    ExperimentConditionCreate,
    ExperimentConditionResponse,
    ExpressionRecordCreate,
    ExpressionRecordResponse,
    KineticRecordCreate,
    KineticRecordResponse,
    LigandResponse,
    MutationRecordResponse,
    PropertyRecordCreate,
    PropertyRankingResponse,
    PropertyRecordResponse,
    StructureCreate,
    StructureArtifactResponse,
    StructureResponse,
    SubstrateCreate,
    SubstrateResponse,
)
from app.schemas.experiment import (
    ExperimentImportPreviewResponse,
    ExperimentImportRecordPreview,
    ExperimentImportRequest,
    ExperimentImportResponse,
)
from app.schemas.job import AnalysisJobCreate, JobResponse
from app.services.experiment_import import (
    ExperimentImportError,
    parse_experiment_csv,
    parse_experiment_xlsx,
    validate_experiment_rows,
)
from app.services.object_storage import store_structure_file
from app.services.property_ranking import build_property_ranking
from app.services.property_standardization import standardize_property_value
from app.services.structure_parser import StructureParseError, parse_structure_text
from app.services.mutations import (
    MutationParseError,
    normalize_mutation_string,
    parse_mutation_string,
    validate_mutations_against_sequence,
)
from worker.jobs import (
    run_conservation_profile,
    run_homology_collection,
    run_library_design,
    run_msa,
    run_mutation_recommendation,
    run_rosetta_ddg,
)


router = APIRouter(prefix="/enzymes", tags=["enzyme records"])

ANALYSIS_ARTIFACT_TYPES = {
    "homolog_sequences",
    "msa",
    "multiple_sequence_alignment",
    "conservation",
    "conservation_profile",
    "mutation_recommendations",
    "rosetta_ddg",
    "mutation_library",
}

ANALYSIS_JOB_TYPES = {
    "homolog_collection",
    "msa",
    "conservation_profile",
    "mutation_recommendation",
    "rosetta_ddg",
    "library_design",
}


def _get_enzyme(db: Session, enzyme_id: str) -> EnzymeEntry:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")
    return enzyme


def _get_engineering_sequence(db: Session, enzyme_id: str) -> str:
    protein_sequence = db.scalar(
        select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme_id)
    )
    if protein_sequence is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="protein sequence not found for analysis job",
        )
    return protein_sequence.mature_sequence or protein_sequence.sequence


def _get_owned_project(db: Session, project_id: str, user_id: str) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_user_id == user_id)
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


def _homologs_from_artifact(db: Session, enzyme_id: str, artifact_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.id == artifact_id,
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "homolog_sequences",
        )
    ).first()
    if row is None:
        return []

    _artifact, job = row
    return _homologs_from_job_summary(job.result_summary_json)


def _latest_homologs_for_msa(db: Session, enzyme_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "homolog_sequences",
        )
        .order_by(AnalysisArtifact.created_at.desc())
    ).first()
    if row is None:
        return []

    _artifact, job = row
    return _homologs_from_job_summary(job.result_summary_json)


def _homologs_from_job_summary(result_summary_json: dict | None) -> list[dict]:
    summary = result_summary_json or {}
    raw_homologs = summary.get("homologs", [])
    if not isinstance(raw_homologs, list):
        return []

    homologs = []
    for index, homolog in enumerate(raw_homologs):
        if not isinstance(homolog, dict) or not homolog.get("sequence"):
            continue
        identifier = homolog.get("identifier") or homolog.get("accession") or f"homolog_{index + 1}"
        homologs.append(
            {
                "identifier": str(identifier),
                "accession": str(homolog.get("accession") or ""),
                "organism": str(homolog.get("organism") or ""),
                "sequence": str(homolog["sequence"]),
                "identity": homolog.get("identity"),
                "coverage": homolog.get("coverage"),
            }
        )
    return homologs


def _custom_fasta_homologs_for_msa(custom_fasta: str) -> list[dict]:
    records = _parse_msa_fasta(custom_fasta)
    return [
        {
            "identifier": record["identifier"],
            "sequence": str(record["aligned_sequence"]).replace("-", ""),
        }
        for record in records
        if record.get("identifier") and str(record.get("aligned_sequence") or "").replace("-", "")
    ]


def _parse_msa_fasta(msa_fasta: str) -> list[dict]:
    records = []
    current_identifier: str | None = None
    current_sequence: list[str] = []

    def flush_record() -> None:
        if current_identifier and current_sequence:
            records.append(
                {
                    "identifier": current_identifier,
                    "aligned_sequence": "".join(current_sequence),
                }
            )

    for line in msa_fasta.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            flush_record()
            header = stripped[1:].strip()
            current_identifier = header.split()[0] if header else None
            current_sequence = []
            continue
        if current_identifier:
            current_sequence.append(stripped)

    flush_record()
    return records


def _latest_msa_records_for_conservation(db: Session, enzyme_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type.in_(("msa", "multiple_sequence_alignment")),
        )
        .order_by(AnalysisArtifact.created_at.desc())
    ).first()
    if row is None:
        return []

    _artifact, job = row
    summary = job.result_summary_json or {}
    msa_fasta = summary.get("msa_fasta")
    if not isinstance(msa_fasta, str) or not msa_fasta.strip():
        return []
    return _parse_msa_fasta(msa_fasta)


def _msa_records_from_artifact(db: Session, enzyme_id: str, artifact_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.id == artifact_id,
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type.in_(("msa", "multiple_sequence_alignment")),
        )
    ).first()
    if row is None:
        return []

    _artifact, job = row
    summary = job.result_summary_json or {}
    msa_fasta = summary.get("msa_fasta")
    if not isinstance(msa_fasta, str) or not msa_fasta.strip():
        return []
    return _parse_msa_fasta(msa_fasta)


def _latest_conservation_sites_for_recommendation(db: Session, enzyme_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "conservation_profile",
        )
        .order_by(AnalysisArtifact.created_at.desc())
    ).first()
    if row is None:
        return []

    _artifact, job = row
    summary = job.result_summary_json or {}
    sites = summary.get("sites", [])
    if not isinstance(sites, list):
        return []
    return [site for site in sites if isinstance(site, dict)]


def _conservation_sites_from_artifact(db: Session, enzyme_id: str, artifact_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.id == artifact_id,
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "conservation_profile",
        )
    ).first()
    if row is None:
        return []

    _artifact, job = row
    summary = job.result_summary_json or {}
    sites = summary.get("sites", [])
    if not isinstance(sites, list):
        return []
    return [site for site in sites if isinstance(site, dict)]


def _latest_recommendation_candidates_for_library(db: Session, enzyme_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "mutation_recommendations",
        )
        .order_by(AnalysisArtifact.created_at.desc())
    ).first()
    if row is None:
        return []

    _artifact, job = row
    summary = job.result_summary_json or {}
    candidates = summary.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _recommendation_candidates_from_artifact(db: Session, enzyme_id: str, artifact_id: str) -> list[dict]:
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.id == artifact_id,
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "mutation_recommendations",
        )
    ).first()
    if row is None:
        return []

    _artifact, job = row
    summary = job.result_summary_json or {}
    candidates = summary.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _rosetta_results_for_library(db: Session, enzyme_id: str) -> list[dict]:
    rows = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type == "rosetta_ddg",
        )
        .order_by(AnalysisArtifact.created_at)
    ).all()

    results = []
    for _artifact, job in rows:
        summary = job.result_summary_json or {}
        if summary.get("mutation_string"):
            results.append(summary)
    return results


def _mutation_records_for_scoring(db: Session, enzyme_id: str) -> list[dict]:
    records = db.scalars(
        select(MutationRecord)
        .where(
            MutationRecord.enzyme_entry_id == enzyme_id,
            MutationRecord.visibility == Visibility.PUBLIC,
        )
        .order_by(MutationRecord.created_at)
    ).all()
    return [
        {
            "mutation_string": record.mutation_string,
            "mutation_positions": _mutation_positions_response(record),
            "property_delta": record.property_delta,
            "source": (record.assay_condition_summary or {}).get("source"),
        }
        for record in records
    ]


def _structure_summaries_for_scoring(db: Session, enzyme_id: str) -> list[dict]:
    structures = db.scalars(
        select(StructureEntry)
        .where(StructureEntry.enzyme_entry_id == enzyme_id)
        .order_by(StructureEntry.created_at.desc())
    ).all()
    return [
        {
            "id": structure.id,
            "structure_type": structure.structure_type,
            "complex_state": structure.complex_state,
            "source": structure.source,
            "chain_summary": structure.chain_summary,
            "ligand_summary": structure.ligand_summary,
        }
        for structure in structures
    ]


def _analysis_job_parameters(
    db: Session,
    enzyme_id: str,
    job_type: str,
    sequence: str,
    requested_parameters: dict | None = None,
) -> dict:
    parameters = {"requested_from": "enzyme_analysis_page"}
    if requested_parameters:
        parameters.update(requested_parameters)
    if job_type == "homolog_collection":
        parameters["search_mode"] = str(parameters.get("search_mode") or "metadata_search")
        parameters["identity_min"] = int(parameters.get("identity_min") or 40)
        parameters["identity_max"] = int(parameters.get("identity_max") or 95)
        parameters["coverage_min"] = int(parameters.get("coverage_min") or 70)
        parameters["max_sequences"] = int(parameters.get("max_sequences") or 25)
    if job_type == "msa":
        custom_fasta = parameters.pop("custom_fasta", None)
        homolog_artifact_id = parameters.get("homolog_artifact_id")
        if isinstance(custom_fasta, str) and custom_fasta.strip():
            homologs = _custom_fasta_homologs_for_msa(custom_fasta)
            parameters["homolog_source"] = {"type": "custom_fasta", "sequence_count": len(homologs)}
        elif isinstance(homolog_artifact_id, str) and homolog_artifact_id.strip():
            homologs = _homologs_from_artifact(db, enzyme_id, homolog_artifact_id)
            parameters["homolog_source"] = {
                "type": "homolog_artifact",
                "artifact_id": homolog_artifact_id,
                "sequence_count": len(homologs),
            }
        else:
            homologs = _latest_homologs_for_msa(db, enzyme_id)
            if homologs:
                parameters["homolog_source"] = {"type": "latest_homolog_artifact", "sequence_count": len(homologs)}
        if homologs:
            parameters["homologs"] = homologs
    if job_type == "conservation_profile":
        msa_artifact_id = parameters.get("msa_artifact_id")
        if isinstance(msa_artifact_id, str) and msa_artifact_id.strip():
            aligned_records = _msa_records_from_artifact(db, enzyme_id, msa_artifact_id)
            parameters["msa_source"] = {
                "type": "msa_artifact",
                "artifact_id": msa_artifact_id,
                "sequence_count": len(aligned_records),
            }
        else:
            aligned_records = _latest_msa_records_for_conservation(db, enzyme_id)
            if aligned_records:
                parameters["msa_source"] = {
                    "type": "latest_msa_artifact",
                    "sequence_count": len(aligned_records),
                }
        parameters["aligned_records"] = aligned_records or [
            {"identifier": "query", "aligned_sequence": sequence},
        ]
    if job_type == "mutation_recommendation":
        conservation_artifact_id = parameters.get("conservation_artifact_id")
        if isinstance(conservation_artifact_id, str) and conservation_artifact_id.strip():
            conservation_sites = _conservation_sites_from_artifact(db, enzyme_id, conservation_artifact_id)
            parameters["conservation_source"] = {
                "type": "conservation_artifact",
                "artifact_id": conservation_artifact_id,
                "site_count": len(conservation_sites),
            }
        else:
            conservation_sites = _latest_conservation_sites_for_recommendation(db, enzyme_id)
            if conservation_sites:
                parameters["conservation_source"] = {
                    "type": "latest_conservation_artifact",
                    "site_count": len(conservation_sites),
                }
        parameters["conservation_sites"] = conservation_sites
        parameters["mutation_records"] = _mutation_records_for_scoring(db, enzyme_id)
        parameters["rosetta_results"] = _rosetta_results_for_library(db, enzyme_id)
        parameters["structure_summaries"] = _structure_summaries_for_scoring(db, enzyme_id)
    if job_type == "rosetta_ddg":
        try:
            mutations = parse_mutation_string(str(parameters.get("mutation_string") or ""))
            validate_mutations_against_sequence(mutations, sequence)
        except MutationParseError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        parameters["mutation_string"] = normalize_mutation_string(mutations)
        parameters["parsed_mutations"] = [mutation.model_dump() for mutation in mutations]
    if job_type == "library_design":
        recommendation_artifact_id = parameters.get("recommendation_artifact_id")
        if isinstance(recommendation_artifact_id, str) and recommendation_artifact_id.strip():
            recommendation_candidates = _recommendation_candidates_from_artifact(
                db,
                enzyme_id,
                recommendation_artifact_id,
            )
            parameters["recommendation_source"] = {
                "type": "recommendation_artifact",
                "artifact_id": recommendation_artifact_id,
                "candidate_count": len(recommendation_candidates),
            }
        else:
            recommendation_candidates = _latest_recommendation_candidates_for_library(db, enzyme_id)
            if recommendation_candidates:
                parameters["recommendation_source"] = {
                    "type": "latest_recommendation_artifact",
                    "candidate_count": len(recommendation_candidates),
                }
        parameters["recommendation_candidates"] = recommendation_candidates
        parameters["rosetta_results"] = _rosetta_results_for_library(db, enzyme_id)
        parameters["library_size"] = int(parameters.get("library_size") or 24)
        parameters["max_order"] = int(parameters.get("max_order") or 2)
        parameters["plate_format"] = int(parameters.get("plate_format") or 96)
    return parameters


def _enqueue_analysis_job(job_type: str, job_id: str) -> None:
    if job_type == "homolog_collection":
        run_homology_collection.delay(job_id)
        return
    if job_type == "msa":
        run_msa.delay(job_id)
        return
    if job_type == "conservation_profile":
        run_conservation_profile.delay(job_id)
        return
    if job_type == "mutation_recommendation":
        run_mutation_recommendation.delay(job_id)
        return
    if job_type == "rosetta_ddg":
        run_rosetta_ddg.delay(job_id)
        return
    if job_type == "library_design":
        run_library_design.delay(job_id)
        return
    raise ValueError(f"unsupported analysis job type: {job_type}")


def _artifact_content_from_summary(
    artifact: AnalysisArtifact,
    job: AnalysisJob | None,
) -> AnalysisArtifactContentResponse:
    summary = job.result_summary_json if job is not None else {}
    summary = summary or {}
    content_text: str | None = None
    content_json: dict | None = None

    if artifact.artifact_type == "msa":
        content_text = summary.get("msa_fasta")
        content_json = {}
    elif artifact.artifact_type == "conservation_profile":
        content_json = {
            "sequence_count": summary.get("sequence_count"),
            "site_count": summary.get("site_count"),
            "sites": summary.get("sites", []),
        }
    elif artifact.artifact_type == "homolog_sequences":
        content_json = {
            "homolog_count": summary.get("homolog_count"),
            "homologs": summary.get("homologs", []),
            "diagnostics": summary.get("diagnostics"),
        }
    elif artifact.artifact_type == "mutation_recommendations":
        content_json = {
            "candidate_count": summary.get("candidate_count"),
            "candidates": summary.get("candidates", []),
        }
    elif artifact.artifact_type == "rosetta_ddg":
        content_json = {
            "mutation_string": summary.get("mutation_string"),
            "mutation_file": summary.get("mutation_file"),
            "parsed_mutations": summary.get("parsed_mutations", []),
            "ddg_kcal_per_mol": summary.get("ddg_kcal_per_mol"),
            "interpretation": summary.get("interpretation"),
            "structure_id": summary.get("structure_id"),
            "runner": summary.get("runner"),
        }
    elif artifact.artifact_type == "mutation_library":
        content_json = {
            "library_size": summary.get("library_size"),
            "plate_format": summary.get("plate_format"),
            "variant_count": summary.get("variant_count"),
            "variants": summary.get("variants", []),
            "plate_layout": summary.get("plate_layout", []),
            "csv_text": summary.get("csv_text", ""),
        }

    if content_json is not None:
        runner = summary.get("runner")
        provenance = summary.get("provenance")
        if isinstance(runner, dict):
            content_json["runner"] = runner
        if isinstance(provenance, dict):
            content_json["provenance"] = provenance

    if content_text is None and content_json is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artifact content not available",
        )

    return AnalysisArtifactContentResponse(
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        content_type=artifact.content_type,
        object_key=artifact.object_key,
        content_text=content_text,
        content_json=content_json,
    )


def _validate_substrate(db: Session, enzyme: EnzymeEntry, substrate_entry_id: str | None) -> None:
    if substrate_entry_id is None:
        return
    substrate = db.get(SubstrateEntry, substrate_entry_id)
    if substrate is None or substrate.enzyme_entry_id not in (None, enzyme.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="substrate not found")


def _condition_response(condition: ExperimentCondition | None) -> ExperimentConditionResponse | None:
    if condition is None:
        return None
    return ExperimentConditionResponse.model_validate(condition)


def _expression_response(
    expression: ExpressionRecord,
    condition: ExperimentCondition | None,
) -> ExpressionRecordResponse:
    return ExpressionRecordResponse(
        id=expression.id,
        enzyme_entry_id=expression.enzyme_entry_id,
        expression_host=expression.expression_host,
        vector=expression.vector,
        expression_level_original=expression.expression_level_original,
        expression_level_standardized=expression.expression_level_standardized,
        soluble_expression=expression.soluble_expression,
        unit_original=expression.unit_original,
        unit_standardized=expression.unit_standardized,
        condition_id=expression.condition_id,
        condition=_condition_response(condition),
        reference_id=expression.reference_id,
        visibility=expression.visibility,
        curation_status=expression.curation_status,
    )


def _structure_response(
    structure: StructureEntry,
    ligands: list[LigandEntry],
    artifact: AnalysisArtifact | None = None,
) -> StructureResponse:
    return StructureResponse(
        id=structure.id,
        enzyme_entry_id=structure.enzyme_entry_id,
        structure_type=structure.structure_type,
        complex_state=structure.complex_state,
        pdb_id=structure.pdb_id,
        chain_summary=structure.chain_summary,
        ligand_summary=structure.ligand_summary,
        artifact_id=structure.artifact_id,
        artifact=StructureArtifactResponse.model_validate(artifact) if artifact is not None else None,
        source=structure.source,
        ligands=[LigandResponse.model_validate(ligand) for ligand in ligands],
    )


def _property_ranking_response(ranking) -> PropertyRankingResponse:
    return PropertyRankingResponse(
        property_type=ranking.property_type,
        ranking_mode=ranking.ranking_mode,
        items=[item.__dict__ for item in ranking.items],
        groups=[
            {
                "condition_key": group.condition_key,
                "items": [item.__dict__ for item in group.items],
            }
            for group in ranking.groups
        ],
        comparison_warnings=ranking.comparison_warnings,
    )


def _mutation_positions_response(record: MutationRecord) -> list[dict]:
    if isinstance(record.mutation_positions, list):
        return record.mutation_positions
    if isinstance(record.mutation_positions, dict):
        mutations = record.mutation_positions.get("mutations")
        if isinstance(mutations, list):
            return mutations

    try:
        return [mutation.model_dump() for mutation in parse_mutation_string(record.mutation_string)]
    except MutationParseError:
        return []


def _mutation_response(record: MutationRecord) -> MutationRecordResponse:
    return MutationRecordResponse(
        id=record.id,
        enzyme_entry_id=record.enzyme_entry_id,
        parent_enzyme_entry_id=record.parent_enzyme_entry_id,
        mutation_string=record.mutation_string,
        mutation_positions=_mutation_positions_response(record),
        effect_summary=record.effect_summary,
        property_delta=record.property_delta,
        substrate=record.substrate,
        assay_condition_summary=record.assay_condition_summary,
        reference_id=record.reference_id,
        is_user_uploaded=record.is_user_uploaded,
        visibility=record.visibility,
        curation_status=record.curation_status,
    )


def _mutation_record_matches_position(record: MutationRecord, position: int | None) -> bool:
    if position is None:
        return True
    return any(
        mutation.get("position") == position for mutation in _mutation_positions_response(record)
    )


def _mutation_record_matches_source(record: MutationRecord, source: str | None) -> bool:
    if not source:
        return True
    if not isinstance(record.assay_condition_summary, dict):
        return False
    record_source = str(record.assay_condition_summary.get("source") or "")
    return source.lower() in record_source.lower()


def _mutation_record_matches_property_delta(
    record: MutationRecord,
    property_delta_key: str | None,
    beneficial_only: bool,
) -> bool:
    if not property_delta_key and not beneficial_only:
        return True
    if not isinstance(record.property_delta, dict):
        return False
    if property_delta_key and property_delta_key not in record.property_delta:
        return False
    if not beneficial_only:
        return True

    values = (
        [record.property_delta[property_delta_key]]
        if property_delta_key
        else record.property_delta.values()
    )
    return any(_is_beneficial_delta_value(value) for value in values)


def _is_beneficial_delta_value(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    try:
        return float(str(value)) > 0
    except (TypeError, ValueError):
        return str(value).lower() in {"improved", "beneficial", "increase", "increased"}


@router.get("/{enzyme_id}/substrates", response_model=list[SubstrateResponse])
def list_substrates(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[SubstrateEntry]:
    _get_enzyme(db, enzyme_id)
    return list(
        db.scalars(
            select(SubstrateEntry)
            .where(SubstrateEntry.enzyme_entry_id == enzyme_id)
            .order_by(SubstrateEntry.created_at)
        )
    )


@router.post(
    "/{enzyme_id}/substrates",
    response_model=SubstrateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_substrate(
    enzyme_id: str,
    request: SubstrateCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SubstrateEntry:
    enzyme = _get_enzyme(db, enzyme_id)
    substrate = SubstrateEntry(
        enzyme_family_id=enzyme.family_id,
        enzyme_entry_id=enzyme.id,
        name=request.name,
        substrate_class=request.substrate_class,
        smiles=request.smiles,
        inchi=request.inchi,
        metadata_json=request.metadata_json,
    )
    db.add(substrate)
    db.commit()
    db.refresh(substrate)
    return substrate


@router.get("/{enzyme_id}/structures", response_model=list[StructureResponse])
def list_structures(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[StructureResponse]:
    _get_enzyme(db, enzyme_id)
    structures = list(
        db.scalars(
            select(StructureEntry)
            .where(StructureEntry.enzyme_entry_id == enzyme_id)
            .order_by(StructureEntry.created_at)
        )
    )
    return [
        _structure_response(
            structure,
            list(
                db.scalars(
                    select(LigandEntry)
                    .where(LigandEntry.structure_entry_id == structure.id)
                    .order_by(LigandEntry.created_at)
                )
            ),
            db.get(AnalysisArtifact, structure.artifact_id) if structure.artifact_id else None,
        )
        for structure in structures
    ]


@router.post(
    "/{enzyme_id}/structures",
    response_model=StructureResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_structure(
    enzyme_id: str,
    request: StructureCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StructureResponse:
    enzyme = _get_enzyme(db, enzyme_id)
    structure = StructureEntry(
        enzyme_entry_id=enzyme.id,
        structure_type=request.structure_type,
        complex_state=request.complex_state,
        pdb_id=request.pdb_id,
        chain_summary=request.chain_summary,
        ligand_summary=request.ligand_summary,
        source=request.source,
    )
    db.add(structure)
    db.flush()

    ligands = [
        LigandEntry(
            structure_entry_id=structure.id,
            ligand_name=ligand.ligand_name,
            ligand_code=ligand.ligand_code,
            ligand_type=ligand.ligand_type,
            chain_id=ligand.chain_id,
            residue_number=ligand.residue_number,
            smiles=ligand.smiles,
            metadata_json=ligand.metadata_json,
        )
        for ligand in request.ligands
    ]
    db.add_all(ligands)
    db.commit()
    db.refresh(structure)
    for ligand in ligands:
        db.refresh(ligand)
    return _structure_response(structure, ligands)


@router.post(
    "/{enzyme_id}/structures/upload",
    response_model=StructureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_structure(
    enzyme_id: str,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StructureResponse:
    enzyme = _get_enzyme(db, enzyme_id)
    file_name = file.filename or "structure.pdb"
    if not file_name.lower().endswith((".pdb", ".cif")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="only .pdb and .cif structure files are supported",
        )

    content = await file.read()
    try:
        parsed = parse_structure_text(content.decode("utf-8"), file_name=file_name)
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="structure file must be UTF-8 text",
        ) from exc
    except StructureParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    stored = store_structure_file(
        file_name=file_name,
        content=content,
        content_type=file.content_type,
    )
    artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme.id,
        artifact_type="structure_file",
        bucket=str(stored["bucket"]),
        object_key=str(stored["object_key"]),
        checksum=stored["checksum"],
        content_type=stored["content_type"],
        size_bytes=stored["size_bytes"],
        source="user_upload",
        visibility=Visibility.PRIVATE,
    )
    db.add(artifact)
    db.flush()

    structure = StructureEntry(
        enzyme_entry_id=enzyme.id,
        structure_type=parsed.structure_type,
        complex_state=parsed.complex_state,
        chain_summary=parsed.chain_summary,
        ligand_summary=parsed.ligand_summary,
        artifact_id=artifact.id,
        source="user_upload",
    )
    db.add(structure)
    db.flush()

    ligands = [
        LigandEntry(
            structure_entry_id=structure.id,
            ligand_name=ligand["ligand_name"],
            ligand_code=ligand["ligand_code"],
            ligand_type=ligand["ligand_type"],
            chain_id=ligand["chain_id"],
            residue_number=ligand["residue_number"],
            metadata_json={"atom_count": ligand["atom_count"]},
        )
        for ligand in parsed.ligands
    ]
    db.add_all(ligands)
    db.commit()
    db.refresh(artifact)
    db.refresh(structure)
    for ligand in ligands:
        db.refresh(ligand)
    return _structure_response(structure, ligands, artifact)


@router.get("/{enzyme_id}/properties", response_model=list[PropertyRecordResponse])
def list_properties(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[PropertyRecord]:
    _get_enzyme(db, enzyme_id)
    return list(
        db.scalars(
            select(PropertyRecord)
            .where(PropertyRecord.enzyme_entry_id == enzyme_id)
            .order_by(PropertyRecord.created_at)
        )
    )


@router.post(
    "/{enzyme_id}/properties",
    response_model=PropertyRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    enzyme_id: str,
    request: PropertyRecordCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyRecord:
    enzyme = _get_enzyme(db, enzyme_id)
    payload = request.model_dump()
    if (
        payload.get("value_standardized") is None
        and payload.get("unit_standardized") is None
        and payload.get("standardization_status") == "not_attempted"
    ):
        standardized = standardize_property_value(
            request.property_type,
            request.value_original,
            request.unit_original,
        )
        payload["value_standardized"] = standardized.value_standardized
        payload["unit_standardized"] = standardized.unit_standardized
        payload["standardization_status"] = standardized.standardization_status
    record = PropertyRecord(enzyme_entry_id=enzyme.id, **payload)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{enzyme_id}/property-rankings", response_model=PropertyRankingResponse)
def get_property_ranking(
    enzyme_id: str,
    property_type: str,
    ranking_mode: str = "reported_value",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PropertyRankingResponse:
    enzyme = _get_enzyme(db, enzyme_id)
    records = list(
        db.scalars(
            select(PropertyRecord)
            .where(
                PropertyRecord.property_type == property_type,
                PropertyRecord.visibility == Visibility.PUBLIC,
            )
            .order_by(PropertyRecord.created_at)
        )
    )
    enzyme_ids = {record.enzyme_entry_id for record in records}
    enzyme_ids.add(enzyme.id)
    enzymes_by_id = {
        item.id: item
        for item in db.scalars(select(EnzymeEntry).where(EnzymeEntry.id.in_(enzyme_ids)))
    }
    ranking = build_property_ranking(
        [record for record in records if record.enzyme_entry_id in enzymes_by_id],
        enzymes_by_id,
        property_type=property_type,
        ranking_mode=ranking_mode,
    )
    return _property_ranking_response(ranking)


@router.get("/{enzyme_id}/mutations", response_model=list[MutationRecordResponse])
def list_mutations(
    enzyme_id: str,
    position: int | None = None,
    property_delta_key: str | None = None,
    beneficial_only: bool = False,
    source: str | None = None,
    visibility: Visibility = Visibility.PUBLIC,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[MutationRecordResponse]:
    enzyme = _get_enzyme(db, enzyme_id)
    records = list(
        db.scalars(
            select(MutationRecord)
            .where(
                MutationRecord.enzyme_entry_id == enzyme.id,
                MutationRecord.visibility == visibility,
            )
            .order_by(MutationRecord.created_at)
        )
    )
    return [
        _mutation_response(record)
        for record in records
        if _mutation_record_matches_position(record, position)
        and _mutation_record_matches_source(record, source)
        and _mutation_record_matches_property_delta(record, property_delta_key, beneficial_only)
    ]


@router.get("/{enzyme_id}/kinetics", response_model=list[KineticRecordResponse])
def list_kinetics(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[KineticRecord]:
    _get_enzyme(db, enzyme_id)
    return list(
        db.scalars(
            select(KineticRecord)
            .where(KineticRecord.enzyme_entry_id == enzyme_id)
            .order_by(KineticRecord.created_at)
        )
    )


@router.post(
    "/{enzyme_id}/kinetics",
    response_model=KineticRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_kinetic(
    enzyme_id: str,
    request: KineticRecordCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> KineticRecord:
    enzyme = _get_enzyme(db, enzyme_id)
    record = KineticRecord(enzyme_entry_id=enzyme.id, **request.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _create_condition(
    db: Session,
    enzyme: EnzymeEntry,
    request: ExperimentConditionCreate,
) -> ExperimentCondition:
    _validate_substrate(db, enzyme, request.substrate_entry_id)
    condition = ExperimentCondition(
        enzyme_entry_id=enzyme.id,
        substrate_entry_id=request.substrate_entry_id,
        assay_temperature=request.assay_temperature,
        assay_pH=request.assay_pH,
        buffer=request.buffer,
        method=request.method,
        reference_id=request.reference_id,
        metadata_json=request.metadata_json,
    )
    db.add(condition)
    db.flush()
    return condition


@router.get("/{enzyme_id}/expression", response_model=list[ExpressionRecordResponse])
def list_expression(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ExpressionRecordResponse]:
    _get_enzyme(db, enzyme_id)
    expressions = list(
        db.scalars(
            select(ExpressionRecord)
            .where(ExpressionRecord.enzyme_entry_id == enzyme_id)
            .order_by(ExpressionRecord.created_at)
        )
    )
    conditions_by_id = {
        condition.id: condition
        for condition in db.scalars(
            select(ExperimentCondition).where(
                ExperimentCondition.id.in_(
                    [expression.condition_id for expression in expressions if expression.condition_id]
                )
            )
        )
    }
    return [
        _expression_response(expression, conditions_by_id.get(expression.condition_id))
        for expression in expressions
    ]


@router.post(
    "/{enzyme_id}/expression",
    response_model=ExpressionRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_expression(
    enzyme_id: str,
    request: ExpressionRecordCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ExpressionRecordResponse:
    enzyme = _get_enzyme(db, enzyme_id)
    condition: ExperimentCondition | None = None
    condition_id = request.condition_id

    if request.condition is not None:
        condition = _create_condition(db, enzyme, request.condition)
        condition_id = condition.id
    elif condition_id is not None:
        condition = db.get(ExperimentCondition, condition_id)
        if condition is None or condition.enzyme_entry_id not in (None, enzyme.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="condition not found")

    expression = ExpressionRecord(
        enzyme_entry_id=enzyme.id,
        expression_host=request.expression_host,
        vector=request.vector,
        expression_level_original=request.expression_level_original,
        expression_level_standardized=request.expression_level_standardized,
        soluble_expression=request.soluble_expression,
        unit_original=request.unit_original,
        unit_standardized=request.unit_standardized,
        condition_id=condition_id,
        reference_id=request.reference_id,
        visibility=request.visibility,
        curation_status=request.curation_status,
    )
    db.add(expression)
    db.commit()
    db.refresh(expression)
    if condition is not None:
        db.refresh(condition)
    return _expression_response(expression, condition)


def _preview_experiment_import(
    db: Session,
    enzyme: EnzymeEntry,
    request: ExperimentImportRequest,
    user: User,
) -> tuple[ExperimentImportPreviewResponse, list[ExperimentImportRecordPreview]]:
    _get_owned_project(db, request.project_id, user.id)
    sequence = _get_engineering_sequence(db, enzyme.id)
    try:
        parsed = _parse_experiment_import_request(request)
        validated = validate_experiment_rows(parsed.rows, sequence)
    except ExperimentImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    records = [
        ExperimentImportRecordPreview(
            row_number=record.row_number,
            variant_name=record.variant_name,
            mutation_string=record.mutation_string,
            sequence=record.sequence,
            measured_property=record.measured_property,
            measured_value=record.measured_value,
            unit=record.unit,
            assay_condition_json=record.assay_condition_json,
            visibility=record.visibility,
        )
        for record in validated.records
    ]
    response = ExperimentImportPreviewResponse(
        fields=parsed.fields,
        row_count=len(parsed.rows),
        record_count=len(records),
        records=records,
    )
    return response, records


def _parse_experiment_import_request(request: ExperimentImportRequest):
    if request.file_content_base64:
        if not request.file_name:
            raise ExperimentImportError("file_name is required for encoded uploads")
        try:
            file_bytes = base64.b64decode(request.file_content_base64, validate=True)
        except ValueError as exc:
            raise ExperimentImportError("file_content_base64 is invalid") from exc

        file_name = request.file_name.lower()
        if file_name.endswith(".xlsx"):
            return parse_experiment_xlsx(file_bytes)
        if file_name.endswith(".csv"):
            return parse_experiment_csv(file_bytes.decode("utf-8-sig"))
        raise ExperimentImportError("unsupported experiment upload file type")

    if request.csv_text is None or not request.csv_text.strip():
        raise ExperimentImportError("csv_text or file_content_base64 is required")
    return parse_experiment_csv(request.csv_text)


@router.post(
    "/{enzyme_id}/experiments/import-preview",
    response_model=ExperimentImportPreviewResponse,
)
def preview_experiment_import(
    enzyme_id: str,
    request: ExperimentImportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ExperimentImportPreviewResponse:
    enzyme = _get_enzyme(db, enzyme_id)
    response, _records = _preview_experiment_import(db, enzyme, request, user)
    return response


@router.post(
    "/{enzyme_id}/experiments/import",
    response_model=ExperimentImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_experiments(
    enzyme_id: str,
    request: ExperimentImportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ExperimentImportResponse:
    enzyme = _get_enzyme(db, enzyme_id)
    _response, records = _preview_experiment_import(db, enzyme, request, user)
    experiments = [
        UserExperiment(
            project_id=request.project_id,
            enzyme_entry_id=enzyme.id,
            variant_name=record.variant_name,
            mutation_string=record.mutation_string,
            sequence=record.sequence,
            measured_property=record.measured_property,
            measured_value=record.measured_value,
            unit=record.unit,
            assay_condition_json=record.assay_condition_json,
            visibility=Visibility(record.visibility),
            curation_status=CurationStatus.UNREVIEWED,
            created_by=user.id,
        )
        for record in records
    ]
    db.add_all(experiments)
    db.commit()
    for experiment in experiments:
        db.refresh(experiment)
    return ExperimentImportResponse(
        created_count=len(experiments),
        experiment_ids=[experiment.id for experiment in experiments],
    )


@router.post("/{enzyme_id}/analysis-jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_analysis_job(
    enzyme_id: str,
    request: AnalysisJobCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    enzyme = _get_enzyme(db, enzyme_id)
    if request.job_type not in ANALYSIS_JOB_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported analysis job type")

    sequence = _get_engineering_sequence(db, enzyme.id)
    job = AnalysisJob(
        enzyme_entry_id=enzyme.id,
        job_type=request.job_type,
        status=JobStatus.QUEUED,
        parameters_json=_analysis_job_parameters(
            db,
            enzyme.id,
            request.job_type,
            sequence,
            request.parameters_json,
        ),
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _enqueue_analysis_job(job.job_type, job.id)
    return job


@router.get("/{enzyme_id}/analysis-artifacts", response_model=list[AnalysisArtifactResponse])
def list_analysis_artifacts(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisArtifactResponse]:
    _get_enzyme(db, enzyme_id)
    rows = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .outerjoin(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type.in_(ANALYSIS_ARTIFACT_TYPES),
        )
        .order_by(AnalysisArtifact.created_at)
    ).all()
    return [
        AnalysisArtifactResponse(
            id=artifact.id,
            enzyme_entry_id=artifact.enzyme_entry_id,
            job_id=artifact.job_id,
            job_status=job.status.value if job is not None else None,
            artifact_type=artifact.artifact_type,
            bucket=artifact.bucket,
            object_key=artifact.object_key,
            checksum=artifact.checksum,
            content_type=artifact.content_type,
            size_bytes=artifact.size_bytes,
            source=artifact.source,
            visibility=artifact.visibility.value,
            created_at=artifact.created_at,
            result_summary_json=job.result_summary_json if job is not None else None,
        )
        for artifact, job in rows
    ]


@router.get(
    "/{enzyme_id}/analysis-artifacts/{artifact_id}/content",
    response_model=AnalysisArtifactContentResponse,
)
def get_analysis_artifact_content(
    enzyme_id: str,
    artifact_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisArtifactContentResponse:
    _get_enzyme(db, enzyme_id)
    row = db.execute(
        select(AnalysisArtifact, AnalysisJob)
        .outerjoin(AnalysisJob, AnalysisJob.id == AnalysisArtifact.job_id)
        .where(
            AnalysisArtifact.id == artifact_id,
            AnalysisArtifact.enzyme_entry_id == enzyme_id,
            AnalysisArtifact.artifact_type.in_(ANALYSIS_ARTIFACT_TYPES),
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    artifact, job = row
    return _artifact_content_from_summary(artifact, job)
