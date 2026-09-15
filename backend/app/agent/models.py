from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.tools.definitions import ToolDefinition

ChatRole = Literal["system", "user", "assistant", "tool"]
AgentStatus = Literal[
    "completed",
    "max_steps",
    "tool_budget_exceeded",
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
    max_steps: int = Field(default=10, ge=1)
    max_total_tokens: int = Field(default=49_152, ge=1)
    max_tool_calls_per_step: int = Field(default=3, ge=1)
    max_tool_budget_retries: int = Field(default=1, ge=0, le=2)
    max_parallel_tools: int = Field(default=3, ge=1)
    context_char_budget: int = Field(default=24_000, ge=4000)
    keep_recent_tool_results: int = Field(default=6, ge=1, le=20)
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
    type: Literal["text_delta", "text_reset", "step", "completed"]
    text_delta: str | None = None
    step: AgentStep | None = None
    result: AgentRunResult | None = None
