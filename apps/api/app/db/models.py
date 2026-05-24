import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    USER = "user"
    CURATOR = "curator"
    ADMIN = "admin"


class ProjectMemberRole(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"


class EnzymeModule(str, enum.Enum):
    ANTHRAQUINONE_GLYCOSYLTRANSFERASE = "ANTHRAQUINONE_GLYCOSYLTRANSFERASE"
    MICROBIAL_TRANSGLUTAMINASE_MATURE = "MICROBIAL_TRANSGLUTAMINASE_MATURE"


class Visibility(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class CurationStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    target_enzyme_module: Mapped[EnzymeModule | None] = mapped_column(Enum(EnzymeModule))
    default_visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PRIVATE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ProjectMemberRole] = mapped_column(Enum(ProjectMemberRole))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EnzymeFamily(Base):
    __tablename__ = "enzyme_family"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    module: Mapped[EnzymeModule] = mapped_column(Enum(EnzymeModule))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime)


class EnzymeEntry(Base):
    __tablename__ = "enzyme_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    family_id: Mapped[str] = mapped_column(ForeignKey("enzyme_family.id"))
    name: Mapped[str] = mapped_column(String(240))
    organism: Mapped[str | None] = mapped_column(String(240))
    ec_number: Mapped[str | None] = mapped_column(String(40))
    uniprot_id: Mapped[str | None] = mapped_column(String(40), index=True)
    uniprot_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    pdb_id: Mapped[str | None] = mapped_column(String(12), index=True)
    alphafold_id: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(80), default="local")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    family: Mapped[EnzymeFamily] = relationship()


class ProteinSequence(Base):
    __tablename__ = "protein_sequence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    sequence: Mapped[str] = mapped_column(Text)
    mature_sequence: Mapped[str | None] = mapped_column(Text)
    is_engineering_target: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(80))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_job"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    job_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    parameters_json: Mapped[dict | None] = mapped_column(JSON)
    result_summary_json: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_job.id"))
    artifact_type: Mapped[str] = mapped_column(String(80))
    bucket: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(80), default="worker")
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PRIVATE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SearchCacheRecord(Base):
    __tablename__ = "search_cache_record"
    __table_args__ = (
        UniqueConstraint(
            "normalized_query",
            "query_kind",
            "module",
            name="uq_search_cache_query_kind_module",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    query: Mapped[str] = mapped_column(String(500))
    normalized_query: Mapped[str] = mapped_column(String(500), index=True)
    query_kind: Mapped[str] = mapped_column(String(80))
    module: Mapped[EnzymeModule | None] = mapped_column(Enum(EnzymeModule))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(80), default="local")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StructureEntry(Base):
    __tablename__ = "structure_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    structure_type: Mapped[str] = mapped_column(String(40))
    complex_state: Mapped[str] = mapped_column(String(40), default="unknown")
    pdb_id: Mapped[str | None] = mapped_column(String(12))
    chain_summary: Mapped[dict | None] = mapped_column(JSON)
    ligand_summary: Mapped[dict | None] = mapped_column(JSON)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_artifact.id"))
    source: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LigandEntry(Base):
    __tablename__ = "ligand_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    structure_entry_id: Mapped[str] = mapped_column(ForeignKey("structure_entry.id"))
    ligand_name: Mapped[str] = mapped_column(String(240))
    ligand_code: Mapped[str | None] = mapped_column(String(40))
    ligand_type: Mapped[str] = mapped_column(String(80), default="unknown")
    chain_id: Mapped[str | None] = mapped_column(String(20))
    residue_number: Mapped[str | None] = mapped_column(String(40))
    smiles: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LiteratureReference(Base):
    __tablename__ = "literature_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(String(240))
    year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(200))
    pubmed_id: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(80), default="manual")
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SubstrateEntry(Base):
    __tablename__ = "substrate_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_family_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_family.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    user_experiment_id: Mapped[str | None] = mapped_column(ForeignKey("user_experiment.id"))
    name: Mapped[str] = mapped_column(String(240))
    substrate_class: Mapped[str | None] = mapped_column(String(120))
    smiles: Mapped[str | None] = mapped_column(Text)
    inchi: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExperimentCondition(Base):
    __tablename__ = "experiment_condition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    substrate_entry_id: Mapped[str | None] = mapped_column(ForeignKey("substrate_entry.id"))
    assay_temperature: Mapped[str | None] = mapped_column(String(80))
    assay_pH: Mapped[str | None] = mapped_column(String(80))
    buffer: Mapped[str | None] = mapped_column(String(240))
    method: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PropertyRecord(Base):
    __tablename__ = "property_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    property_type: Mapped[str] = mapped_column(String(80))
    value_original: Mapped[str] = mapped_column(String(120))
    unit_original: Mapped[str | None] = mapped_column(String(80))
    value_standardized: Mapped[str | None] = mapped_column(String(120))
    unit_standardized: Mapped[str | None] = mapped_column(String(80))
    standardization_status: Mapped[str] = mapped_column(String(40), default="not_attempted")
    substrate: Mapped[str | None] = mapped_column(String(240))
    assay_temperature: Mapped[str | None] = mapped_column(String(80))
    assay_pH: Mapped[str | None] = mapped_column(String(80))
    buffer: Mapped[str | None] = mapped_column(String(240))
    method: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExpressionRecord(Base):
    __tablename__ = "expression_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    expression_host: Mapped[str | None] = mapped_column(String(160))
    vector: Mapped[str | None] = mapped_column(String(160))
    expression_level_original: Mapped[str | None] = mapped_column(String(120))
    expression_level_standardized: Mapped[str | None] = mapped_column(String(120))
    soluble_expression: Mapped[str | None] = mapped_column(String(120))
    unit_original: Mapped[str | None] = mapped_column(String(80))
    unit_standardized: Mapped[str | None] = mapped_column(String(80))
    condition_id: Mapped[str | None] = mapped_column(ForeignKey("experiment_condition.id"))
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KineticRecord(Base):
    __tablename__ = "kinetic_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    substrate: Mapped[str | None] = mapped_column(String(240))
    km: Mapped[str | None] = mapped_column(String(120))
    kcat: Mapped[str | None] = mapped_column(String(120))
    kcat_km: Mapped[str | None] = mapped_column(String(120))
    unit_original: Mapped[str | None] = mapped_column(String(120))
    assay_temperature: Mapped[str | None] = mapped_column(String(80))
    assay_pH: Mapped[str | None] = mapped_column(String(80))
    method: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MutationRecord(Base):
    __tablename__ = "mutation_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    parent_enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    mutation_string: Mapped[str] = mapped_column(String(240))
    mutation_positions: Mapped[dict | None] = mapped_column(JSON)
    effect_summary: Mapped[str | None] = mapped_column(Text)
    property_delta: Mapped[dict | None] = mapped_column(JSON)
    substrate: Mapped[str | None] = mapped_column(String(240))
    assay_condition_summary: Mapped[dict | None] = mapped_column(JSON)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    is_user_uploaded: Mapped[bool] = mapped_column(default=False)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserExperiment(Base):
    __tablename__ = "user_experiment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    variant_name: Mapped[str] = mapped_column(String(200))
    mutation_string: Mapped[str | None] = mapped_column(String(240))
    sequence: Mapped[str | None] = mapped_column(Text)
    measured_property: Mapped[str] = mapped_column(String(120))
    measured_value: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(80))
    assay_condition_json: Mapped[dict | None] = mapped_column(JSON)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PRIVATE)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VisibilityRequest(Base):
    __tablename__ = "visibility_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    requested_visibility: Mapped[Visibility] = mapped_column(Enum(Visibility))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)


class CurationTask(Base):
    __tablename__ = "curation_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    visibility_request_id: Mapped[str] = mapped_column(ForeignKey("visibility_request.id"))
    status: Mapped[str] = mapped_column(String(40), default="open")
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
