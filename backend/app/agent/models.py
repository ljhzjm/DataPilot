from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.tools.definitions import ToolDefinition

ChatRole = Literal["system", "user", "assistant", "tool"]
AgentStatus = Literal[
    "completed",
    "max_steps",
    "token_budget_exceeded",
    "loop_detected",
]


class ToolCall(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: ChatRole
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class TokenUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str | None = None


class ChatModel(Protocol):
    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse: ...


class StreamingChatModel(Protocol):
    def chat_stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[Any]: ...


class ToolExecution(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None
    duration_ms: float = Field(ge=0)


class AgentStep(BaseModel):
    step: int = Field(ge=1)
    assistant_content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_executions: list[ToolExecution] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class AgentConfig(BaseModel):
    max_steps: int = Field(default=8, ge=1)
    max_total_tokens: int = Field(default=8192, ge=1)
    parallel_tool_calls: bool = True
    stream_model: bool = True
    max_tool_result_chars: int = Field(default=16_000, ge=256)


class AgentRunResult(BaseModel):
    status: AgentStatus
    output: str | None = None
    termination_reason: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class AgentStreamEvent(BaseModel):
    type: Literal["text_delta", "step", "completed"]
    text_delta: str | None = None
    step: AgentStep | None = None
    result: AgentRunResult | None = None
