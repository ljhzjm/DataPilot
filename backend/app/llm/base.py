from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from app.agent.models import ChatMessage, LLMResponse, TokenUsage
from app.tools.definitions import ToolDefinition


class ToolCallDelta(BaseModel):
    index: int = Field(ge=0)
    id: str | None = None
    name: str | None = None
    arguments_delta: str | None = None


class StreamEvent(BaseModel):
    type: Literal["text_delta", "tool_call_delta", "usage", "finish"]
    content_delta: str | None = None
    tool_call_delta: ToolCallDelta | None = None
    usage: TokenUsage | None = None
    finish_reason: str | None = None


class EmbeddingResult(BaseModel):
    model: str
    embeddings: list[list[float]]
    usage: TokenUsage = Field(default_factory=TokenUsage)


class LLMProvider(Protocol):
    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "default",
    ) -> LLMResponse: ...

    def chat_stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "default",
    ) -> AsyncIterator[StreamEvent]: ...

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "embedding",
    ) -> EmbeddingResult: ...

    async def close(self) -> None: ...


class LLMGatewayError(RuntimeError):
    pass


class LLMResponseError(LLMGatewayError):
    pass
