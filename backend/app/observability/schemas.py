from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.chat.schemas import MessageView


class UsageRecordView(BaseModel):
    id: UUID
    request_id: str
    trace_id: UUID | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    task: str
    provider: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    latency_ms: float = Field(ge=0)
    success: bool
    error_type: str | None = None
    created_at: datetime


class UsageSummary(BaseModel):
    call_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    average_latency_ms: float = Field(ge=0)
    error_count: int = Field(ge=0)


class UsagePage(BaseModel):
    items: list[UsageRecordView] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ToolMetrics(BaseModel):
    call_count: int = Field(ge=0)
    failed_call_count: int = Field(ge=0)
    total_duration_ms: float = Field(ge=0)


class TraceView(BaseModel):
    trace_id: UUID
    conversation_id: UUID | None = None
    assistant_message: MessageView | None = None
    usage_records: list[UsageRecordView] = Field(default_factory=list)
    tool_metrics: ToolMetrics
