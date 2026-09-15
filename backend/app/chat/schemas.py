from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.agent.models import AgentStep

MessageRole = Literal["system", "user", "assistant", "tool"]
MessageStatus = Literal["streaming", "completed", "aborted", "error"]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageView(BaseModel):
    id: UUID
    role: MessageRole
    content: str | None = None
    status: MessageStatus
    tool_calls: list[dict[str, object]] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    created_at: datetime


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    message_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    id: UUID
    title: str
    messages: list[MessageView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
