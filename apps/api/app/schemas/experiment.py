from pydantic import BaseModel, ConfigDict


class ExperimentImportRequest(BaseModel):
    project_id: str
    csv_text: str | None = None
    file_name: str | None = None
    file_content_base64: str | None = None


class ExperimentImportRecordPreview(BaseModel):
    row_number: int
    variant_name: str
    mutation_string: str | None = None
    sequence: str | None = None
    measured_property: str
    measured_value: str
    unit: str | None = None
    assay_condition_json: dict[str, str]
    visibility: str


class ExperimentImportPreviewResponse(BaseModel):
    fields: list[str]
    row_count: int
    record_count: int
    records: list[ExperimentImportRecordPreview]


class ExperimentImportResponse(BaseModel):
    created_count: int
    experiment_ids: list[str]


class UserExperimentResponse(BaseModel):
    id: str
    project_id: str
    enzyme_entry_id: str | None = None
    variant_name: str
    mutation_string: str | None = None
    sequence: str | None = None
    measured_property: str
    measured_value: str
    unit: str | None = None
    assay_condition_json: dict | None = None
    visibility: str
    curation_status: str
    created_by: str

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
