import asyncio
import json
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.agent.models import (
    AgentConfig,
    AgentRunResult,
    AgentStep,
    ChatMessage,
    ChatModel,
    TokenUsage,
    ToolCall,
    ToolExecution,
)
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
    ) -> AgentRunResult:
        messages: list[ChatMessage] = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=user_input))

        usage = TokenUsage()
        steps: list[AgentStep] = []
        previous_signature: tuple[tuple[str, str], ...] | None = None
        tool_definitions = self._tools.definitions()

        for step_number in range(1, self._config.max_steps + 1):
            response = await self._model.chat(messages=messages, tools=tool_definitions)
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
                steps.append(step)
                return AgentRunResult(
                    status="completed",
                    output=response.content,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )

            if usage.total_tokens > self._config.max_total_tokens:
                steps.append(step)
                reason = (
                    f"已达到 Token 预算：已使用 {usage.total_tokens}，"
                    f"预算为 {self._config.max_total_tokens}。"
                )
                return AgentRunResult(
                    status="token_budget_exceeded",
                    output=reason,
                    termination_reason=reason,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )

            current_signature = self._call_signature(response.tool_calls)
            if previous_signature == current_signature:
                steps.append(step)
                reason = "检测到连续重复的工具调用，已停止 Agent 以避免循环。"
                return AgentRunResult(
                    status="loop_detected",
                    output=reason,
                    termination_reason=reason,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )

            executions = await self._execute_tool_calls(response.tool_calls)
            step.tool_executions = executions
            steps.append(step)

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
        return AgentRunResult(
            status="max_steps",
            output=reason,
            termination_reason=reason,
            messages=messages,
            steps=steps,
            usage=usage,
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
    def _call_signature(calls: Sequence[ToolCall]) -> tuple[tuple[str, str], ...]:
        return tuple(
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
