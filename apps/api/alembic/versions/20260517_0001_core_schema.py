"""core schema

Revision ID: 20260517_0001
Revises:
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "20260517_0001"
down_revision = None
branch_labels = None
depends_on = None


USER_ROLE = sa.Enum("USER", "CURATOR", "ADMIN", name="userrole")
PROJECT_MEMBER_ROLE = sa.Enum("OWNER", "MEMBER", name="projectmemberrole")
ENZYME_MODULE = sa.Enum(
    "ANTHRAQUINONE_GLYCOSYLTRANSFERASE",
    "MICROBIAL_TRANSGLUTAMINASE_MATURE",
    name="enzymemodule",
)
VISIBILITY = sa.Enum("PRIVATE", "PUBLIC", name="visibility")
CURATION_STATUS = sa.Enum(
    "UNREVIEWED", "PENDING", "APPROVED", "REJECTED", name="curationstatus"
)
JOB_STATUS = sa.Enum("QUEUED", "RUNNING", "FINISHED", "FAILED", "CANCELLED", name="jobstatus")


def uuid_pk() -> sa.Column[str]:
    return sa.Column("id", sa.String(length=36), nullable=False)


def upgrade() -> None:
    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("role", USER_ROLE, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "enzyme_family",
        uuid_pk(),
        sa.Column("module", ENZYME_MODULE, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module"),
    )

    op.create_table(
        "literature_reference",
        uuid_pk(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("journal", sa.String(length=240), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=200), nullable=True),
        sa.Column("pubmed_id", sa.String(length=80), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "projects",
        uuid_pk(),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_enzyme_module", ENZYME_MODULE, nullable=True),
        sa.Column("default_visibility", VISIBILITY, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "enzyme_entry",
        uuid_pk(),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("organism", sa.String(length=240), nullable=True),
        sa.Column("ec_number", sa.String(length=40), nullable=True),
        sa.Column("uniprot_id", sa.String(length=40), nullable=True),
        sa.Column("pdb_id", sa.String(length=12), nullable=True),
        sa.Column("alphafold_id", sa.String(length=80), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["enzyme_family.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_enzyme_entry_pdb_id"), "enzyme_entry", ["pdb_id"], unique=False)
    op.create_index(
        op.f("ix_enzyme_entry_uniprot_id"), "enzyme_entry", ["uniprot_id"], unique=False
    )

    op.create_table(
        "project_members",
        uuid_pk(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", PROJECT_MEMBER_ROLE, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )

    op.create_table(
        "visibility_request",
        uuid_pk(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("requested_visibility", VISIBILITY, nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "protein_sequence",
        uuid_pk(),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Text(), nullable=False),
        sa.Column("mature_sequence", sa.Text(), nullable=True),
        sa.Column("is_engineering_target", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_protein_sequence_checksum"), "protein_sequence", ["checksum"])

    op.create_table(
        "analysis_job",
        uuid_pk(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", JOB_STATUS, nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("result_summary_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "property_record",
        uuid_pk(),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_type", sa.String(length=80), nullable=False),
        sa.Column("value_original", sa.String(length=120), nullable=False),
        sa.Column("unit_original", sa.String(length=80), nullable=True),
        sa.Column("value_standardized", sa.String(length=120), nullable=True),
        sa.Column("unit_standardized", sa.String(length=80), nullable=True),
        sa.Column("standardization_status", sa.String(length=40), nullable=False),
        sa.Column("substrate", sa.String(length=240), nullable=True),
        sa.Column("assay_temperature", sa.String(length=80), nullable=True),
        sa.Column("assay_pH", sa.String(length=80), nullable=True),
        sa.Column("buffer", sa.String(length=240), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("curation_status", CURATION_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["reference_id"], ["literature_reference.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "kinetic_record",
        uuid_pk(),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("substrate", sa.String(length=240), nullable=True),
        sa.Column("km", sa.String(length=120), nullable=True),
        sa.Column("kcat", sa.String(length=120), nullable=True),
        sa.Column("kcat_km", sa.String(length=120), nullable=True),
        sa.Column("unit_original", sa.String(length=120), nullable=True),
        sa.Column("assay_temperature", sa.String(length=80), nullable=True),
        sa.Column("assay_pH", sa.String(length=80), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("curation_status", CURATION_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["reference_id"], ["literature_reference.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mutation_record",
        uuid_pk(),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("parent_enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("mutation_string", sa.String(length=240), nullable=False),
        sa.Column("mutation_positions", sa.JSON(), nullable=True),
        sa.Column("effect_summary", sa.Text(), nullable=True),
        sa.Column("property_delta", sa.JSON(), nullable=True),
        sa.Column("substrate", sa.String(length=240), nullable=True),
        sa.Column("assay_condition_summary", sa.JSON(), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("is_user_uploaded", sa.Boolean(), nullable=False),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("curation_status", CURATION_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["parent_enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["reference_id"], ["literature_reference.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "analysis_artifact",
        uuid_pk(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("bucket", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_job.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_experiment",
        uuid_pk(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("variant_name", sa.String(length=200), nullable=False),
        sa.Column("mutation_string", sa.String(length=240), nullable=True),
        sa.Column("sequence", sa.Text(), nullable=True),
        sa.Column("measured_property", sa.String(length=120), nullable=False),
        sa.Column("measured_value", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=True),
        sa.Column("assay_condition_json", sa.JSON(), nullable=True),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("curation_status", CURATION_STATUS, nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "curation_task",
        uuid_pk(),
        sa.Column("visibility_request_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("assigned_to", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
        sa.ForeignKeyConstraint(["visibility_request_id"], ["visibility_request.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_log",
        uuid_pk(),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "structure_entry",
        uuid_pk(),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("structure_type", sa.String(length=40), nullable=False),
        sa.Column("complex_state", sa.String(length=40), nullable=False),
        sa.Column("pdb_id", sa.String(length=12), nullable=True),
        sa.Column("chain_summary", sa.JSON(), nullable=True),
        sa.Column("ligand_summary", sa.JSON(), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["analysis_artifact.id"]),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("structure_entry")
    op.drop_table("audit_log")
    op.drop_table("curation_task")
    op.drop_table("user_experiment")
    op.drop_table("analysis_artifact")
    op.drop_table("mutation_record")
    op.drop_table("kinetic_record")
    op.drop_table("property_record")
    op.drop_table("analysis_job")
    op.drop_index(op.f("ix_protein_sequence_checksum"), table_name="protein_sequence")
    op.drop_table("protein_sequence")
    op.drop_table("visibility_request")
    op.drop_table("project_members")
    op.drop_index(op.f("ix_enzyme_entry_uniprot_id"), table_name="enzyme_entry")
    op.drop_index(op.f("ix_enzyme_entry_pdb_id"), table_name="enzyme_entry")
    op.drop_table("enzyme_entry")
    op.drop_table("projects")
    op.drop_table("literature_reference")
    op.drop_table("enzyme_family")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
