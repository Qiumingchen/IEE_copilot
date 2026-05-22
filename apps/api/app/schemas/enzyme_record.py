from datetime import datetime
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


class StructureArtifactResponse(BaseModel):
    id: str
    bucket: str
    object_key: str
    checksum: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None

    model_config = ConfigDict(from_attributes=True)


class StructureResponse(BaseModel):
    id: str
    enzyme_entry_id: str
    structure_type: str
    complex_state: str
    pdb_id: str | None = None
    chain_summary: dict[str, Any] | None = None
    ligand_summary: dict[str, Any] | None = None
    artifact_id: str | None = None
    artifact: StructureArtifactResponse | None = None
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
    reference: "LiteratureReferenceResponse | None" = None

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class CuratedEvidenceImportRequest(BaseModel):
    csv_text: str


class CuratedEvidencePreviewRecord(BaseModel):
    row_number: int
    record_type: str
    summary: str
    reference_key: str | None = None
    reference_match_mode: str | None = None
    evidence_text: str | None = None


class CuratedEvidencePreviewError(BaseModel):
    row_number: int
    field: str
    message: str


class CuratedEvidencePreviewResponse(BaseModel):
    fields: list[str]
    row_count: int
    record_counts: dict[str, int]
    records: list[CuratedEvidencePreviewRecord] = Field(default_factory=list)
    errors: list[CuratedEvidencePreviewError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    valid: bool = True


class LiteratureReferenceResponse(BaseModel):
    id: str
    title: str
    authors: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None
    source: str
    provenance: dict[str, Any] | None = None


class CuratedEvidenceImportResponse(BaseModel):
    created: dict[str, int]
    reference_ids: list[str] = Field(default_factory=list)
    references: list[LiteratureReferenceResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PropertyRankingItemResponse(BaseModel):
    rank: int
    enzyme_entry_id: str
    enzyme_name: str
    property_record_id: str
    value_original: str
    unit_original: str | None = None
    value_standardized: str | None = None
    unit_standardized: str | None = None
    standardization_status: str
    substrate: str | None = None
    assay_temperature: str | None = None
    assay_pH: str | None = None
    method: str | None = None
    reference_id: str | None = None


class PropertyRankingGroupResponse(BaseModel):
    condition_key: dict[str, Any]
    items: list[PropertyRankingItemResponse]


class PropertyRankingResponse(BaseModel):
    property_type: str
    ranking_mode: str
    items: list[PropertyRankingItemResponse] = Field(default_factory=list)
    groups: list[PropertyRankingGroupResponse] = Field(default_factory=list)
    comparison_warnings: list[str] = Field(default_factory=list)


class MutationRecordResponse(BaseModel):
    id: str
    enzyme_entry_id: str
    parent_enzyme_entry_id: str | None = None
    mutation_string: str
    mutation_positions: list[dict[str, Any]] = Field(default_factory=list)
    effect_summary: str | None = None
    property_delta: dict[str, Any] | None = None
    substrate: str | None = None
    assay_condition_summary: dict[str, Any] | None = None
    reference_id: str | None = None
    reference: LiteratureReferenceResponse | None = None
    is_user_uploaded: bool
    visibility: Visibility
    curation_status: CurationStatus

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
    reference: LiteratureReferenceResponse | None = None

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
    reference: LiteratureReferenceResponse | None = None
    visibility: Visibility
    curation_status: CurationStatus

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class AnalysisArtifactResponse(BaseModel):
    id: str
    enzyme_entry_id: str | None = None
    job_id: str | None = None
    job_status: str | None = None
    artifact_type: str
    bucket: str
    object_key: str
    checksum: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    source: str
    visibility: str
    created_at: datetime
    result_summary_json: dict[str, Any] | None = None


class AnalysisArtifactContentResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    content_type: str | None = None
    object_key: str
    content_text: str | None = None
    content_json: dict[str, Any] | None = None
