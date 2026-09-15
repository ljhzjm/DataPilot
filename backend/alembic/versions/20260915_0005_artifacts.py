"""Add sandbox artifact metadata.

Revision ID: 20260915_0005
Revises: 20260915_0004
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260915_0005"
down_revision: str | None = "20260915_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_artifacts_created_at",
        "artifacts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_artifacts_created_at", table_name="artifacts")
    op.drop_table("artifacts")
