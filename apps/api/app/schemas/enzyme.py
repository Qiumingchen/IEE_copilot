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


class PdbDiscoveryChain(BaseModel):
    chain_id: str
    sequence: str
    residue_count: int
    mapping_quality: str | None = None


class PdbDiscoveryMetadata(BaseModel):
    pdb_id: str | None = None
    title: str | None = None
    enzyme_name: str | None = None
    organism: str | None = None
    uniprot_id: str | None = None
    alphafold_id: str | None = None


class PdbDiscoveryHit(BaseModel):
    enzyme: EnzymeSummary
    identity: float
    coverage: float
    aligned_length: int
    evidence: list[str] = Field(default_factory=list)
    confidence: str

    model_config = ConfigDict(from_attributes=True)


class PdbDiscoveryResponse(BaseModel):
    file_name: str
    module: EnzymeModule
    metadata: PdbDiscoveryMetadata
    structure_type: str
    complex_state: str
    chains: list[PdbDiscoveryChain]
    query_chain_id: str
    query_sequence: str
    hits: list[PdbDiscoveryHit] = Field(default_factory=list)
