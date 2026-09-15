from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    title: Mapped[str] = mapped_column(String(160), default="新会话")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
    next_sequence: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.sequence",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_messages_conversation_sequence"),
        UniqueConstraint("request_id", name="uq_messages_request_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    trace_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    steps: Mapped[list["AgentStepRecord"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="AgentStepRecord.step_index",
    )


class AgentStepRecord(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("message_id", "step_index", name="uq_agent_steps_message_index"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    message_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
    )
    step_index: Mapped[int] = mapped_column(Integer)
    assistant_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    tool_executions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    message: Mapped[Message] = relationship(back_populates="steps")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(160))
    original_filename: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(80), unique=True)
    file_type: Mapped[str] = mapped_column(String(16))
    file_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="processing")
    original_path: Mapped[str] = mapped_column(Text)
    parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class LLMUsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    trace_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
    )
