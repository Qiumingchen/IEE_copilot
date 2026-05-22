from pydantic import BaseModel, ConfigDict, Field

from app.db.models import EnzymeModule


class EnzymeSearchRequest(BaseModel):
    query: str
    project_id: str | None = None


class EnzymeSummary(BaseModel):
    id: str
    family_id: str
    name: str
    organism: str | None = None
    ec_number: str | None = None
    uniprot_id: str | None = None
    pdb_id: str | None = None
    alphafold_id: str | None = None
    source: str

    model_config = ConfigDict(from_attributes=True)


class EnzymeSearchResponse(BaseModel):
    enzyme: EnzymeSummary
    matches: list[EnzymeSummary] = Field(default_factory=list)
    job_id: str
    cache_status: str
    query_kind: str
    module: EnzymeModule

    model_config = ConfigDict(use_enum_values=True)
