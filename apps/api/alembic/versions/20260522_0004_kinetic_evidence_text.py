"""Add evidence text to kinetic records.

Revision ID: 20260522_0004
Revises: 20260518_0003
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260522_0004"
down_revision = "20260518_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kinetic_record", sa.Column("evidence_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("kinetic_record", "evidence_text")
