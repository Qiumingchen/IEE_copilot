"""Add Epic 1 enzyme domain models.

Revision ID: 20260518_0002
Revises: 20260517_0001
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260518_0002"
down_revision = "20260517_0001"
branch_labels = None
depends_on = None


VISIBILITY = postgresql.ENUM("PRIVATE", "PUBLIC", name="visibility", create_type=False)
CURATIONSTATUS = postgresql.ENUM(
    "UNREVIEWED",
    "PENDING",
    "APPROVED",
    "REJECTED",
    name="curationstatus",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "ligand_entry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("structure_entry_id", sa.String(length=36), nullable=False),
        sa.Column("ligand_name", sa.String(length=240), nullable=False),
        sa.Column("ligand_code", sa.String(length=40), nullable=True),
        sa.Column("ligand_type", sa.String(length=80), nullable=False),
        sa.Column("chain_id", sa.String(length=20), nullable=True),
        sa.Column("residue_number", sa.String(length=40), nullable=True),
        sa.Column("smiles", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["structure_entry_id"], ["structure_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "substrate_entry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enzyme_family_id", sa.String(length=36), nullable=True),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("user_experiment_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("substrate_class", sa.String(length=120), nullable=True),
        sa.Column("smiles", sa.Text(), nullable=True),
        sa.Column("inchi", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["enzyme_family_id"], ["enzyme_family.id"]),
        sa.ForeignKeyConstraint(["user_experiment_id"], ["user_experiment.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "experiment_condition",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("substrate_entry_id", sa.String(length=36), nullable=True),
        sa.Column("assay_temperature", sa.String(length=80), nullable=True),
        sa.Column("assay_pH", sa.String(length=80), nullable=True),
        sa.Column("buffer", sa.String(length=240), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["reference_id"], ["literature_reference.id"]),
        sa.ForeignKeyConstraint(["substrate_entry_id"], ["substrate_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "expression_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("expression_host", sa.String(length=160), nullable=True),
        sa.Column("vector", sa.String(length=160), nullable=True),
        sa.Column("expression_level_original", sa.String(length=120), nullable=True),
        sa.Column("expression_level_standardized", sa.String(length=120), nullable=True),
        sa.Column("soluble_expression", sa.String(length=120), nullable=True),
        sa.Column("unit_original", sa.String(length=80), nullable=True),
        sa.Column("unit_standardized", sa.String(length=80), nullable=True),
        sa.Column("condition_id", sa.String(length=36), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("visibility", VISIBILITY, nullable=False),
        sa.Column("curation_status", CURATIONSTATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["condition_id"], ["experiment_condition.id"]),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["reference_id"], ["literature_reference.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("expression_record")
    op.drop_table("experiment_condition")
    op.drop_table("substrate_entry")
    op.drop_table("ligand_entry")
