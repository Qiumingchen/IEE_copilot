from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import JobStatus


class JobResponse(BaseModel):
    id: str
    project_id: str | None = None
    enzyme_entry_id: str | None = None
    job_type: str
    status: JobStatus
    parameters_json: dict | None = None
    result_summary_json: dict | None = None
    error_message: str | None = None
    created_by: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class AnalysisJobCreate(BaseModel):
    job_type: str
    parameters_json: dict | None = None
