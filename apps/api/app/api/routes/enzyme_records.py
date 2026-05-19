from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    AnalysisArtifact,
    AnalysisJob,
    EnzymeEntry,
    ExperimentCondition,
    ExpressionRecord,
    KineticRecord,
    LigandEntry,
    JobStatus,
    PropertyRecord,
    ProteinSequence,
    StructureEntry,
    SubstrateEntry,
    User,
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
    PropertyRecordCreate,
    PropertyRecordResponse,
    StructureCreate,
    StructureResponse,
    SubstrateCreate,
    SubstrateResponse,
)
from app.schemas.job import AnalysisJobCreate, JobResponse
from worker.jobs import (
    run_conservation_profile,
    run_homology_collection,
    run_msa,
    run_mutation_recommendation,
)


router = APIRouter(prefix="/enzymes", tags=["enzyme records"])

ANALYSIS_ARTIFACT_TYPES = {
    "homolog_sequences",
    "msa",
    "multiple_sequence_alignment",
    "conservation",
    "conservation_profile",
    "mutation_recommendations",
}

ANALYSIS_JOB_TYPES = {"homolog_collection", "msa", "conservation_profile", "mutation_recommendation"}


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
    summary = job.result_summary_json or {}
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


def _analysis_job_parameters(db: Session, enzyme_id: str, job_type: str, sequence: str) -> dict:
    parameters = {"requested_from": "enzyme_analysis_page"}
    if job_type == "msa":
        homologs = _latest_homologs_for_msa(db, enzyme_id)
        if homologs:
            parameters["homologs"] = homologs
    if job_type == "conservation_profile":
        parameters["aligned_records"] = _latest_msa_records_for_conservation(db, enzyme_id) or [
            {"identifier": "query", "aligned_sequence": sequence},
        ]
    if job_type == "mutation_recommendation":
        parameters["conservation_sites"] = _latest_conservation_sites_for_recommendation(db, enzyme_id)
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
        }
    elif artifact.artifact_type == "mutation_recommendations":
        content_json = {
            "candidate_count": summary.get("candidate_count"),
            "candidates": summary.get("candidates", []),
        }

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
) -> StructureResponse:
    return StructureResponse(
        id=structure.id,
        enzyme_entry_id=structure.enzyme_entry_id,
        structure_type=structure.structure_type,
        complex_state=structure.complex_state,
        pdb_id=structure.pdb_id,
        chain_summary=structure.chain_summary,
        ligand_summary=structure.ligand_summary,
        source=structure.source,
        ligands=[LigandResponse.model_validate(ligand) for ligand in ligands],
    )


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
    record = PropertyRecord(enzyme_entry_id=enzyme.id, **request.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


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
        parameters_json=_analysis_job_parameters(db, enzyme.id, request.job_type, sequence),
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
