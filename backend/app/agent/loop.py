import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel

from app.agent.models import (
    AgentConfig,
    AgentRunResult,
    AgentStep,
    AgentStreamEvent,
    ChatMessage,
    ChatModel,
    LLMResponse,
    StreamingChatModel,
    TokenUsage,
    ToolCall,
    ToolExecution,
)
from app.tools.definitions import ToolDefinition
from app.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self,
        *,
        model: ChatModel,
        tools: ToolRegistry,
        config: AgentConfig | None = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._config = config or AgentConfig()

    async def run(
        self,
        user_input: str,
        *,
        system_prompt: str | None = None,
        history: Sequence[ChatMessage] = (),
    ) -> AgentRunResult:
        async for event in self.stream(
            user_input,
            system_prompt=system_prompt,
            history=history,
        ):
            if event.type == "completed" and event.result is not None:
                return event.result
        raise RuntimeError("Agent stream ended without a completed event.")

    async def stream(
        self,
        user_input: str,
        *,
        system_prompt: str | None = None,
        history: Sequence[ChatMessage] = (),
    ) -> AsyncIterator[AgentStreamEvent]:
        messages: list[ChatMessage] = list(history)
        if system_prompt:
            messages.insert(0, ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=user_input))

        usage = TokenUsage()
        steps: list[AgentStep] = []
        previous_signature: frozenset[tuple[str, str]] | None = None
        tool_definitions = self._tools.definitions()

        for step_number in range(1, self._config.max_steps + 1):
            response, streamed_text = await self._chat_response(
                messages,
                tool_definitions,
            )
            usage = usage + response.usage
            assistant_message = ChatMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_message)

            step = AgentStep(
                step=step_number,
                assistant_content=response.content,
                tool_calls=response.tool_calls,
                usage=response.usage,
            )

            if not response.tool_calls:
                for text_delta in streamed_text:
                    yield AgentStreamEvent(type="text_delta", text_delta=text_delta)
                steps.append(step)
                result = AgentRunResult(
                    status="completed",
                    output=response.content,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )
                yield AgentStreamEvent(type="step", step=step)
                yield AgentStreamEvent(type="completed", result=result)
                return

            if usage.total_tokens > self._config.max_total_tokens:
                steps.append(step)
                reason = (
                    f"已达到 Token 预算：已使用 {usage.total_tokens}，"
                    f"预算为 {self._config.max_total_tokens}。"
                )
                result = AgentRunResult(
                    status="token_budget_exceeded",
                    output=reason,
                    termination_reason=reason,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )
                yield AgentStreamEvent(type="step", step=step)
                yield AgentStreamEvent(type="completed", result=result)
                return

            current_signature = self._call_signature(response.tool_calls)
            repeated_calls = (
                previous_signature.intersection(current_signature)
                if previous_signature is not None
                else set()
            )
            if repeated_calls:
                steps.append(step)
                repeated_names = ", ".join(sorted({name for name, _ in repeated_calls}))
                reason = f"检测到连续重复的工具调用：{repeated_names}。请更换工具或参数后重试。"
                result = AgentRunResult(
                    status="loop_detected",
                    output=reason,
                    termination_reason=reason,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )
                yield AgentStreamEvent(type="step", step=step)
                yield AgentStreamEvent(type="completed", result=result)
                return

            executions = await self._execute_tool_calls(response.tool_calls)
            step.tool_executions = executions
            steps.append(step)
            yield AgentStreamEvent(type="step", step=step)

            for execution in executions:
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=execution.tool_name,
                        tool_call_id=execution.tool_call_id,
                        content=self._serialize_tool_execution(execution),
                    )
                )

            previous_signature = current_signature

        reason = f"已达到最大执行步数 {self._config.max_steps}，Agent 已停止。"
        result = AgentRunResult(
            status="max_steps",
            output=reason,
            termination_reason=reason,
            messages=messages,
            steps=steps,
            usage=usage,
        )
        yield AgentStreamEvent(type="completed", result=result)

    async def _chat_response(
        self,
        messages: Sequence[ChatMessage],
        tool_definitions: Sequence[ToolDefinition],
    ) -> tuple[LLMResponse, list[str]]:
        if not self._config.stream_model or not hasattr(self._model, "chat_stream"):
            return (
                await self._model.chat(
                    messages=messages,
                    tools=tool_definitions,
                ),
                [],
            )

        text_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, str]] = {}
        usage = TokenUsage()
        finish_reason: str | None = None

        streaming_model = cast(StreamingChatModel, self._model)
        stream = streaming_model.chat_stream(
            messages=messages,
            tools=tool_definitions,
        )
        async for event in stream:
            if event.type == "text_delta" and event.content_delta:
                text_parts.append(event.content_delta)
            elif event.type == "tool_call_delta" and event.tool_call_delta is not None:
                index = event.tool_call_delta.index
                builder = tool_call_parts.setdefault(
                    index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if event.tool_call_delta.id:
                    builder["id"] = event.tool_call_delta.id
                if event.tool_call_delta.name:
                    builder["name"] = event.tool_call_delta.name
                if event.tool_call_delta.arguments_delta:
                    builder["arguments"] += event.tool_call_delta.arguments_delta
            elif event.type == "usage" and event.usage is not None:
                usage = event.usage
            elif event.type == "finish":
                finish_reason = event.finish_reason

        tool_calls = _assemble_tool_calls(tool_call_parts)
        return (
            LLMResponse(
                content="".join(text_parts) if not tool_calls else None,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=finish_reason,
            ),
            text_parts,
        )

    async def _execute_tool_calls(self, calls: Sequence[ToolCall]) -> list[ToolExecution]:
        tools = [self._tools.get(call.name) for call in calls]
        can_run_in_parallel = self._config.parallel_tool_calls and all(
            tool is not None and tool.parallel_safe for tool in tools
        )

        if can_run_in_parallel:
            return list(await asyncio.gather(*(self._execute_one(call) for call in calls)))

        executions: list[ToolExecution] = []
        for call in calls:
            executions.append(await self._execute_one(call))
        return executions

    async def _execute_one(self, call: ToolCall) -> ToolExecution:
        started = perf_counter()
        try:
            tool = self._tools.get(call.name)
            if tool is None:
                raise KeyError(f"Unknown tool: {call.name}")
            result = await tool.invoke(call.arguments)
            return ToolExecution(
                tool_call_id=call.id,
                tool_name=call.name,
                arguments=call.arguments,
                result=result,
                duration_ms=(perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ToolExecution(
                tool_call_id=call.id,
                tool_name=call.name,
                arguments=call.arguments,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=(perf_counter() - started) * 1000,
            )

    def _serialize_tool_execution(self, execution: ToolExecution) -> str:
        payload = {
            "ok": execution.error is None,
            "result": execution.result,
            "error": execution.error,
        }
        serialized = json.dumps(
            self._jsonable(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        limit = self._config.max_tool_result_chars
        if len(serialized) <= limit:
            return serialized
        return serialized[:limit]

    @staticmethod
    def _call_signature(calls: Sequence[ToolCall]) -> frozenset[tuple[str, str]]:
        return frozenset(
            (
                call.name,
                json.dumps(call.arguments, ensure_ascii=True, sort_keys=True, default=str),
            )
            for call in calls
        )

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._jsonable(item) for item in value]
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, (Decimal, UUID)):
            return str(value)
        return value


def _assemble_tool_calls(
    parts: dict[int, dict[str, str]],
) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index in sorted(parts):
        part = parts[index]
        if not part["name"]:
            continue
        try:
            arguments = json.loads(part["arguments"] or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool call arguments must be a JSON object.")
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid streamed tool call arguments: {exc}") from exc
        calls.append(
            ToolCall(
                id=part["id"] or f"stream-call-{index}",
                name=part["name"],
                arguments=arguments,
            )
        )
    return calls
