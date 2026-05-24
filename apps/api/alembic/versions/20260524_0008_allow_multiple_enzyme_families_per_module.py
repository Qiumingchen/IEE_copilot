"""Allow multiple enzyme families per legacy module.

Revision ID: 20260524_0008
Revises: 20260522_0004
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260524_0008"
down_revision = "20260522_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("enzyme_family"):
        if constraint.get("column_names") == ["module"]:
            op.drop_constraint(constraint["name"], "enzyme_family", type_="unique")
            break


def downgrade() -> None:
    op.create_unique_constraint("uq_enzyme_family_module", "enzyme_family", ["module"])
