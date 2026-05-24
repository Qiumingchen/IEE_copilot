"""add uniprot reviewed flag

Revision ID: 20260524_0009
Revises: 20260524_0008
Create Date: 2026-05-24 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260524_0009"
down_revision: str | None = "20260524_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "enzyme_entry",
        sa.Column("uniprot_reviewed", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
    op.execute(
        "UPDATE enzyme_entry SET uniprot_reviewed = true "
        "WHERE uniprot_id IS NOT NULL AND lower(source) LIKE '%swiss%'"
    )
    op.alter_column("enzyme_entry", "uniprot_reviewed", nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_column("enzyme_entry", "uniprot_reviewed")
