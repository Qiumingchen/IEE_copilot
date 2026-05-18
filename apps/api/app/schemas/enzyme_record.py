from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import CurationStatus, Visibility


class SubstrateCreate(BaseModel):
    name: str
    substrate_class: str | None = None
    smiles: str | None = None
    inchi: str | None = None
    metadata_json: dict[str, Any] | None = None


class SubstrateResponse(SubstrateCreate):
    id: str
    enzyme_family_id: str | None = None
    enzyme_entry_id: str | None = None
    user_experiment_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LigandCreate(BaseModel):
    ligand_name: str
    ligand_code: str | None = None
    ligand_type: str = "unknown"
    chain_id: str | None = None
    residue_number: str | None = None
    smiles: str | None = None
    metadata_json: dict[str, Any] | None = None


class LigandResponse(LigandCreate):
    id: str
    structure_entry_id: str

    model_config = ConfigDict(from_attributes=True)


class StructureCreate(BaseModel):
    structure_type: str
    complex_state: str = "unknown"
    pdb_id: str | None = None
    chain_summary: dict[str, Any] | None = None
    ligand_summary: dict[str, Any] | None = None
    source: str = "user_upload"
    ligands: list[LigandCreate] = Field(default_factory=list)


class StructureResponse(BaseModel):
    id: str
    enzyme_entry_id: str
    structure_type: str
    complex_state: str
    pdb_id: str | None = None
    chain_summary: dict[str, Any] | None = None
    ligand_summary: dict[str, Any] | None = None
    source: str
    ligands: list[LigandResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PropertyRecordCreate(BaseModel):
    property_type: str
    value_original: str
    unit_original: str | None = None
    value_standardized: str | None = None
    unit_standardized: str | None = None
    standardization_status: str = "not_attempted"
    substrate: str | None = None
    assay_temperature: str | None = None
    assay_pH: str | None = None
    buffer: str | None = None
    method: str | None = None
    reference_id: str | None = None
    evidence_text: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    curation_status: CurationStatus = CurationStatus.UNREVIEWED


class PropertyRecordResponse(PropertyRecordCreate):
    id: str
    enzyme_entry_id: str

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class KineticRecordCreate(BaseModel):
    substrate: str | None = None
    km: str | None = None
    kcat: str | None = None
    kcat_km: str | None = None
    unit_original: str | None = None
    assay_temperature: str | None = None
    assay_pH: str | None = None
    method: str | None = None
    reference_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    curation_status: CurationStatus = CurationStatus.UNREVIEWED


class KineticRecordResponse(KineticRecordCreate):
    id: str
    enzyme_entry_id: str

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ExperimentConditionCreate(BaseModel):
    substrate_entry_id: str | None = None
    assay_temperature: str | None = None
    assay_pH: str | None = None
    buffer: str | None = None
    method: str | None = None
    reference_id: str | None = None
    metadata_json: dict[str, Any] | None = None


class ExperimentConditionResponse(ExperimentConditionCreate):
    id: str
    enzyme_entry_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ExpressionRecordCreate(BaseModel):
    expression_host: str | None = None
    vector: str | None = None
    expression_level_original: str | None = None
    expression_level_standardized: str | None = None
    soluble_expression: str | None = None
    unit_original: str | None = None
    unit_standardized: str | None = None
    condition_id: str | None = None
    condition: ExperimentConditionCreate | None = None
    reference_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    curation_status: CurationStatus = CurationStatus.UNREVIEWED


class ExpressionRecordResponse(BaseModel):
    id: str
    enzyme_entry_id: str
    expression_host: str | None = None
    vector: str | None = None
    expression_level_original: str | None = None
    expression_level_standardized: str | None = None
    soluble_expression: str | None = None
    unit_original: str | None = None
    unit_standardized: str | None = None
    condition_id: str | None = None
    condition: ExperimentConditionResponse | None = None
    reference_id: str | None = None
    visibility: Visibility
    curation_status: CurationStatus

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
