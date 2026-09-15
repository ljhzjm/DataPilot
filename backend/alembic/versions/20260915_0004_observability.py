"""Add trace IDs and persistent LLM usage records.

Revision ID: 20260915_0004
Revises: 20260915_0003
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260915_0004"
down_revision: str | None = "20260915_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_messages_trace_id", "messages", ["trace_id"], unique=False)
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=18, scale=8),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        "ix_usage_records_created_at",
        "usage_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_trace_id",
        "usage_records",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_conversation_id",
        "usage_records",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_message_id",
        "usage_records",
        ["message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_records_message_id", table_name="usage_records")
    op.drop_index("ix_usage_records_conversation_id", table_name="usage_records")
    op.drop_index("ix_usage_records_trace_id", table_name="usage_records")
    op.drop_index("ix_usage_records_created_at", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("ix_messages_trace_id", table_name="messages")
    op.drop_column("messages", "trace_id")
