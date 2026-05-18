from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    EnzymeEntry,
    ExperimentCondition,
    ExpressionRecord,
    KineticRecord,
    LigandEntry,
    PropertyRecord,
    StructureEntry,
    SubstrateEntry,
    User,
)
from app.db.session import get_db
from app.schemas.enzyme_record import (
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


router = APIRouter(prefix="/enzymes", tags=["enzyme records"])


def _get_enzyme(db: Session, enzyme_id: str) -> EnzymeEntry:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")
    return enzyme


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
