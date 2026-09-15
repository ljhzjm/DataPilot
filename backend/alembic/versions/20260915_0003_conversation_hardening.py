"""Add atomic sequence allocation and conversation archiving.

Revision ID: 20260915_0003
Revises: 20260915_0002
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260915_0003"
down_revision: str | None = "20260915_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "next_sequence",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE conversations AS conversation
        SET next_sequence = COALESCE(
            (
                SELECT MAX(message.sequence) + 1
                FROM messages AS message
                WHERE message.conversation_id = conversation.id
            ),
            1
        )
        """
    )
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_archived_at",
        "conversations",
        ["archived_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_archived_at", table_name="conversations")
    op.drop_index("ix_conversations_updated_at", table_name="conversations")
    op.drop_column("conversations", "archived_at")
    op.drop_column("conversations", "next_sequence")
