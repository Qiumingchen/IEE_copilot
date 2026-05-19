"""Add search cache records.

Revision ID: 20260518_0003
Revises: 20260518_0002
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260518_0003"
down_revision = "20260518_0002"
branch_labels = None
depends_on = None


ENZYMEMODULE = postgresql.ENUM(
    "ANTHRAQUINONE_GLYCOSYLTRANSFERASE",
    "MICROBIAL_TRANSGLUTAMINASE_MATURE",
    name="enzymemodule",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "search_cache_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("normalized_query", sa.String(length=500), nullable=False),
        sa.Column("query_kind", sa.String(length=80), nullable=False),
        sa.Column("module", ENZYMEMODULE, nullable=True),
        sa.Column("enzyme_entry_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["enzyme_entry_id"], ["enzyme_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_query",
            "query_kind",
            "module",
            name="uq_search_cache_query_kind_module",
        ),
    )
    op.create_index(
        op.f("ix_search_cache_record_normalized_query"),
        "search_cache_record",
        ["normalized_query"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_search_cache_record_normalized_query"), table_name="search_cache_record")
    op.drop_table("search_cache_record")
