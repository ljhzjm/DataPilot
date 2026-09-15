import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from app.agent import Agent, AgentConfig, ChatMessage, LLMResponse, TokenUsage, ToolCall
from app.llm.base import StreamEvent, ToolCallDelta
from app.tools.definitions import ToolDefinition
from app.tools.registry import ToolRegistry, tool


class ScriptedModel:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[list[ChatMessage], list[ToolDefinition]]] = []

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        self.calls.append((list(messages), list(tools)))
        return self._responses.pop(0)


class StreamingScriptedModel:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        raise AssertionError("chat() should not be used for a streaming model")

    async def chat_stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[StreamEvent]:
        del messages, tools
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(
                type="tool_call_delta",
                tool_call_delta=ToolCallDelta(
                    index=0,
                    id="call-1",
                    name="echo",
                    arguments_delta='{"value":9}',
                ),
            )
            yield StreamEvent(
                type="usage",
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            )
            yield StreamEvent(type="finish", finish_reason="tool_calls")
        else:
            yield StreamEvent(type="text_delta", content_delta="结果")
            yield StreamEvent(
                type="usage",
                usage=TokenUsage(input_tokens=6, output_tokens=1),
            )
            yield StreamEvent(type="finish", finish_reason="stop")


@pytest.mark.asyncio
async def test_agent_streams_tool_call_and_final_text() -> None:
    model = StreamingScriptedModel()
    agent = Agent(model=model, tools=make_registry())
    events = [event async for event in agent.stream("返回值")]

    assert [event.type for event in events] == [
        "step",
        "text_delta",
        "step",
        "completed",
    ]
    assert events[0].step is not None
    assert events[0].step.tool_executions[0].result == {"value": 9}
    assert events[1].text_delta == "结果"
    assert events[3].result is not None
    assert events[3].result.output == "结果"


def make_registry(on_call: Any | None = None) -> ToolRegistry:
    registry = ToolRegistry()

    @tool(
        name="echo",
        description=(
            "做什么：返回输入值。"
            "何时使用：测试工具调用循环。"
            "参数 value：待返回的整数。"
            '示例：{"value":1}。'
        ),
    )
    async def echo(value: int) -> dict[str, int]:
        if on_call is not None:
            await on_call()
        return {"value": value}

    registry.register(echo)
    return registry


@pytest.mark.asyncio
async def test_agent_executes_tool_and_returns_final_answer() -> None:
    model = ScriptedModel(
        [
            LLMResponse(
                tool_calls=[ToolCall(id="call-1", name="echo", arguments={"value": 7})],
                usage=TokenUsage(input_tokens=10, output_tokens=3),
            ),
            LLMResponse(
                content="分析完成",
                usage=TokenUsage(input_tokens=12, output_tokens=4),
            ),
        ]
    )
    agent = Agent(model=model, tools=make_registry(), config=AgentConfig(max_total_tokens=100))

    result = await agent.run("返回值是多少")

    assert result.status == "completed"
    assert result.output == "分析完成"
    assert result.usage.total_tokens == 29
    assert len(result.steps) == 2
    assert result.steps[0].tool_executions[0].result == {"value": 7}
    assert model.calls[1][0][-1].role == "tool"
    assert '"value":7' in (model.calls[1][0][-1].content or "")


@pytest.mark.asyncio
async def test_agent_stops_when_token_budget_is_exceeded() -> None:
    executed = False

    async def mark_executed() -> None:
        nonlocal executed
        executed = True

    model = ScriptedModel(
        [
            LLMResponse(
                tool_calls=[ToolCall(id="call-1", name="echo", arguments={"value": 1})],
                usage=TokenUsage(input_tokens=8, output_tokens=3),
            )
        ]
    )
    agent = Agent(
        model=model,
        tools=make_registry(mark_executed),
        config=AgentConfig(max_total_tokens=10),
    )

    result = await agent.run("执行工具")

    assert result.status == "token_budget_exceeded"
    assert result.usage.total_tokens == 11
    assert executed is False
    assert "Token 预算" in (result.termination_reason or "")


@pytest.mark.asyncio
async def test_agent_detects_consecutive_duplicate_tool_calls() -> None:
    execution_count = 0

    async def count_execution() -> None:
        nonlocal execution_count
        execution_count += 1

    repeated_call = ToolCall(id="call-1", name="echo", arguments={"value": 1})
    model = ScriptedModel(
        [
            LLMResponse(tool_calls=[repeated_call]),
            LLMResponse(tool_calls=[repeated_call.model_copy(update={"id": "call-2"})]),
        ]
    )
    agent = Agent(
        model=model,
        tools=make_registry(count_execution),
        config=AgentConfig(max_steps=4),
    )

    result = await agent.run("重复执行")

    assert result.status == "loop_detected"
    assert execution_count == 1
    assert "重复" in (result.termination_reason or "")


@pytest.mark.asyncio
async def test_agent_stops_at_max_steps() -> None:
    model = ScriptedModel(
        [
            LLMResponse(tool_calls=[ToolCall(id="call-1", name="echo", arguments={"value": 1})]),
            LLMResponse(tool_calls=[ToolCall(id="call-2", name="echo", arguments={"value": 2})]),
        ]
    )
    agent = Agent(model=model, tools=make_registry(), config=AgentConfig(max_steps=2))

    result = await agent.run("持续执行")

    assert result.status == "max_steps"
    assert len(result.steps) == 2
    assert "最大执行步数" in (result.termination_reason or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parallel", "expected_max_active"),
    [(True, 2), (False, 1)],
)
async def test_agent_supports_parallel_and_serial_tool_execution(
    parallel: bool,
    expected_max_active: int,
) -> None:
    active = 0
    max_active = 0
    lock = asyncio.Lock()
    registry = ToolRegistry()

    @tool(
        name="slow",
        description=(
            "做什么：等待后返回输入值。"
            "何时使用：测试并发和串行执行。"
            "参数 value：输入整数。"
            '示例：{"value":1}。'
        ),
        parallel_safe=True,
    )
    async def slow(value: int) -> int:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        async with lock:
            active -= 1
        return value

    registry.register(slow)
    model = ScriptedModel(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(id="call-1", name="slow", arguments={"value": 1}),
                    ToolCall(id="call-2", name="slow", arguments={"value": 2}),
                ]
            ),
            LLMResponse(content="完成"),
        ]
    )
    agent = Agent(
        model=model,
        tools=registry,
        config=AgentConfig(parallel_tool_calls=parallel),
    )

    result = await agent.run("并发调用")

    assert result.status == "completed"
    assert max_active == expected_max_active
