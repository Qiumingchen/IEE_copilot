"""Add enzyme literature reference links.

Revision ID: 20260526_0010
Revises: 20260524_0009
Create Date: 2026-05-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260526_0010"
down_revision: str | None = "20260524_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enzyme_literature_reference",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=False),
        sa.Column("literature_reference_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.ForeignKeyConstraint(["literature_reference_id"], ["literature_reference.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "enzyme_entry_id",
            "literature_reference_id",
            name="uq_enzyme_literature_reference",
        ),
    )


def downgrade() -> None:
    op.drop_table("enzyme_literature_reference")
