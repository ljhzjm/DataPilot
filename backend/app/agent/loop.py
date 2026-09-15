from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel
from sqlglot import parse_one
from sqlglot.errors import ParseError

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


@dataclass(frozen=True)
class _CompletedModelResponse:
    response: LLMResponse


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
        executed_signatures: set[tuple[str, str]] = set()
        tool_budget_retries = 0
        tool_definitions = self._tools.definitions()

        for step_number in range(1, self._config.max_steps + 1):
            response: LLMResponse | None = None
            async for item in self._stream_model_response(
                messages,
                tool_definitions,
            ):
                if isinstance(item, AgentStreamEvent):
                    yield item
                else:
                    response = item.response
            if response is None:
                raise RuntimeError("Model stream ended without a response.")
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

            if len(response.tool_calls) > self._config.max_tool_calls_per_step:
                steps.append(step)
                if tool_budget_retries < self._config.max_tool_budget_retries:
                    messages.pop()
                    tool_budget_retries += 1
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                f"本轮提出了 {len(response.tool_calls)} 个工具调用，"
                                f"超过单步上限 {self._config.max_tool_calls_per_step}。"
                                "请不要执行这些调用，重新规划为更少的工具调用；"
                                "优先按关键维度分批分析。"
                            ),
                        )
                    )
                    continue
                reason = (
                    f"单步工具调用数为 {len(response.tool_calls)}，"
                    f"超过上限 {self._config.max_tool_calls_per_step}。"
                    "请缩小分析范围后重试。"
                )
                result = AgentRunResult(
                    status="tool_budget_exceeded",
                    output=reason,
                    termination_reason=reason,
                    messages=messages,
                    steps=steps,
                    usage=usage,
                )
                yield AgentStreamEvent(type="step", step=step)
                yield AgentStreamEvent(type="completed", result=result)
                return

            current_signatures = self._call_signatures(response.tool_calls)
            repeated_calls = executed_signatures.intersection(current_signatures)
            duplicate_in_batch = len(set(current_signatures)) != len(current_signatures)
            if repeated_calls or duplicate_in_batch:
                steps.append(step)
                duplicate_signatures = repeated_calls if repeated_calls else current_signatures
                repeated_names = ", ".join(sorted({name for name, _ in duplicate_signatures}))
                reason = (
                    f"检测到重复的 SQL 或工具调用：{repeated_names}。请更换分析维度或参数后重试。"
                )
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

            executed_signatures.update(current_signatures)
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

    def _compacted_messages(
        self,
        messages: Sequence[ChatMessage],
    ) -> list[ChatMessage]:
        compacted = [message.model_copy(deep=True) for message in messages]
        tool_indexes = [index for index, message in enumerate(compacted) if message.role == "tool"]
        old_tool_indexes = tool_indexes[: -self._config.keep_recent_tool_results]
        for index in old_tool_indexes:
            message = compacted[index]
            compacted[index] = message.model_copy(
                update={
                    "content": _compact_tool_content(
                        message.name or "tool",
                        message.content or "",
                    )
                }
            )

        total_chars = sum(len(message.content or "") for message in compacted)
        if total_chars <= self._config.context_char_budget:
            return compacted

        recent_non_tool = {
            index for index, message in enumerate(compacted) if message.role != "tool"
        }
        recent_non_tool = set(sorted(recent_non_tool)[-6:])
        for index, message in enumerate(compacted):
            if message.role == "tool":
                compacted[index] = message.model_copy(
                    update={
                        "content": _compact_tool_content(
                            message.name or "tool",
                            message.content or "",
                            include_rows=False,
                        )
                    }
                )
            elif index not in recent_non_tool and message.role != "system" and message.content:
                compacted[index] = message.model_copy(update={"content": message.content[:500]})
        return compacted

    async def _stream_model_response(
        self,
        messages: Sequence[ChatMessage],
        tool_definitions: Sequence[ToolDefinition],
    ) -> AsyncIterator[AgentStreamEvent | _CompletedModelResponse]:
        model_messages = self._compacted_messages(messages)
        if not self._config.stream_model or not hasattr(self._model, "chat_stream"):
            response = await self._model.chat(
                messages=model_messages,
                tools=tool_definitions,
            )
            if response.content:
                yield AgentStreamEvent(
                    type="text_delta",
                    text_delta=response.content,
                )
            if response.tool_calls and response.content:
                yield AgentStreamEvent(type="text_reset")
            yield _CompletedModelResponse(response=response)
            return

        text_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, str]] = {}
        usage = TokenUsage()
        finish_reason: str | None = None

        streaming_model = cast(StreamingChatModel, self._model)
        stream = streaming_model.chat_stream(
            messages=model_messages,
            tools=tool_definitions,
        )
        async for event in stream:
            if event.type == "text_delta" and event.content_delta:
                text_parts.append(event.content_delta)
                yield AgentStreamEvent(
                    type="text_delta",
                    text_delta=event.content_delta,
                )
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
        if tool_calls and text_parts:
            yield AgentStreamEvent(type="text_reset")
        yield _CompletedModelResponse(
            response=LLMResponse(
                content="".join(text_parts) if not tool_calls else None,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=finish_reason,
            )
        )

    async def _execute_tool_calls(self, calls: Sequence[ToolCall]) -> list[ToolExecution]:
        tools = [self._tools.get(call.name) for call in calls]
        can_run_in_parallel = (
            self._config.parallel_tool_calls
            and len(calls) <= self._config.max_parallel_tools
            and all(tool is not None and tool.parallel_safe for tool in tools)
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
        if execution.error is None and execution.tool_name == "plot_chart":
            result = execution.result if isinstance(execution.result, dict) else {}
            raw_spec = result.get("spec")
            spec: dict[str, Any] = raw_spec if isinstance(raw_spec, dict) else {}
            payload = {
                "ok": True,
                "result": {
                    "kind": "chart",
                    "title": spec.get("title"),
                    "chart_type": spec.get("type"),
                    "rendered": True,
                },
                "error": None,
            }
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

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
    def _call_signatures(calls: Sequence[ToolCall]) -> list[tuple[str, str]]:
        return [
            (
                call.name,
                _normalized_arguments(call.name, call.arguments),
            )
            for call in calls
        ]

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


def _normalized_arguments(name: str, arguments: dict[str, Any]) -> str:
    normalized = dict(arguments)
    sql = normalized.get("sql")
    if name in {"run_sql", "mcp__query_company_data"} and isinstance(sql, str):
        try:
            expression = parse_one(sql, read="duckdb")
            normalized["sql"] = " ".join(expression.sql(pretty=False).casefold().split())
        except ParseError:
            normalized["sql"] = " ".join(sql.casefold().split())
    return json.dumps(
        normalized,
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )


def _compact_tool_content(
    tool_name: str,
    content: str,
    *,
    include_rows: bool = True,
) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return json.dumps(
            {
                "compacted": True,
                "tool": tool_name,
                "preview": content[:500],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    result = payload.get("result")
    summary: dict[str, Any] = {
        "compacted": True,
        "tool": tool_name,
        "ok": payload.get("ok"),
    }
    if isinstance(result, dict):
        if tool_name in {"run_sql", "mcp__query_company_data"}:
            summary["summary"] = {
                "columns": result.get("columns"),
                "row_count": result.get("row_count"),
                "truncated": result.get("truncated"),
            }
            if include_rows and isinstance(result.get("rows"), list):
                summary["summary"]["sample_rows"] = result["rows"][:2]
        elif tool_name == "get_schema":
            columns = result.get("columns")
            summary["summary"] = {
                "table_name": result.get("table_name"),
                "columns": [
                    {
                        "name": column.get("name"),
                        "data_type": column.get("data_type"),
                    }
                    for column in columns
                    if isinstance(column, dict)
                ]
                if isinstance(columns, list)
                else [],
            }
        elif tool_name == "list_tables":
            summary["summary"] = {
                "tables": result.get("tables"),
                "count": result.get("count"),
            }
        else:
            summary["summary"] = str(result)[:500]
    else:
        summary["summary"] = str(result)[:500]
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
