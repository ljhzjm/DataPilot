from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import pytest

from app.agent.models import (
    AgentRunResult,
    AgentStreamEvent,
    ChatMessage,
    TokenUsage,
)
from app.chat.runtime import AgentChatRuntime, RuntimeEventType


class NonCompletedAgent:
    async def stream(
        self,
        question: str,
        *,
        history: Sequence[ChatMessage],
        system_prompt: str,
        trace_id: UUID | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        del question, history, system_prompt, trace_id
        yield AgentStreamEvent(
            type="completed",
            result=AgentRunResult(
                status="token_budget_exceeded",
                output="已达到 Token 预算。",
                termination_reason="已达到 Token 预算。",
                usage=TokenUsage(input_tokens=100, output_tokens=20),
            ),
        )


@pytest.mark.asyncio
async def test_agent_runtime_converts_non_completed_result_to_error() -> None:
    runtime = AgentChatRuntime(NonCompletedAgent())  # type: ignore[arg-type]
    events = [
        event
        async for event in runtime.stream(
            question="分析",
            history=[],
        )
    ]

    assert len(events) == 1
    assert events[0].type is RuntimeEventType.ERROR
    assert events[0].message == "已达到 Token 预算。"
