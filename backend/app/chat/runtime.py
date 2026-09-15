import asyncio
from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from app.agent.loop import Agent
from app.agent.models import (
    AgentConfig,
    AgentStep,
    ChatMessage,
    TokenUsage,
    ToolExecution,
)
from app.core.config import Settings
from app.llm.router import ModelRouter
from app.tools.registry import ToolRegistry


class RuntimeEventType(StrEnum):
    STEP = "step"
    TEXT = "text"
    TEXT_RESET = "text_reset"
    DONE = "done"
    ERROR = "error"


class RuntimeEvent(BaseModel):
    type: RuntimeEventType
    step: AgentStep | None = None
    text: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ChatRuntime(Protocol):
    def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
        trace_id: UUID | None = None,
    ) -> AsyncIterator[RuntimeEvent]: ...


class AgentChatRuntime:
    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    async def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
        trace_id: UUID | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        async for event in self._agent.stream(
            question,
            history=history,
            system_prompt=_agent_system_prompt(),
            trace_id=trace_id,
        ):
            if event.type == "text_delta" and event.text_delta:
                yield RuntimeEvent(
                    type=RuntimeEventType.TEXT,
                    text=event.text_delta,
                )
            elif event.type == "text_reset":
                yield RuntimeEvent(type=RuntimeEventType.TEXT_RESET)
            elif event.type == "step" and event.step is not None:
                yield RuntimeEvent(
                    type=RuntimeEventType.STEP,
                    step=event.step,
                )
            elif event.type == "completed" and event.result is not None:
                if event.result.status == "completed":
                    yield RuntimeEvent(
                        type=RuntimeEventType.DONE,
                        data={
                            "status": event.result.status,
                            "termination_reason": event.result.termination_reason,
                        },
                    )
                else:
                    yield RuntimeEvent(
                        type=RuntimeEventType.ERROR,
                        message=(
                            event.result.termination_reason
                            or event.result.output
                            or f"Agent stopped with status: {event.result.status}"
                        ),
                    )


class UnavailableChatRuntime:
    async def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
        trace_id: UUID | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        del question, history, trace_id
        yield RuntimeEvent(
            type=RuntimeEventType.ERROR,
            message="真实模型运行时尚未配置。",
        )


class PreviewChatRuntime:
    """Development-only trace used to exercise the UI before the LLM gateway exists."""

    async def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
        trace_id: UUID | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        del history, trace_id
        await asyncio.sleep(0.15)
        yield RuntimeEvent(
            type=RuntimeEventType.STEP,
            step=_preview_step(
                step=1,
                thought="检查当前示例数据结构，确认可分析字段。",
                tool_name="get_schema",
                arguments={"table_name": "sales"},
                result={
                    "table_name": "sales",
                    "columns": [
                        {"name": "region", "data_type": "VARCHAR", "nullable": True},
                        {"name": "amount", "data_type": "BIGINT", "nullable": True},
                    ],
                    "sample_rows": [
                        {"region": "East", "amount": 120},
                        {"region": "West", "amount": 80},
                    ],
                },
                duration_ms=18,
            ),
        )
        await asyncio.sleep(0.15)
        yield RuntimeEvent(
            type=RuntimeEventType.STEP,
            step=_preview_step(
                step=2,
                thought="按区域聚合销售额。",
                tool_name="run_sql",
                arguments={
                    "sql": (
                        "SELECT region, SUM(amount) AS total "
                        "FROM sales GROUP BY region ORDER BY region"
                    )
                },
                result={
                    "columns": ["region", "total"],
                    "rows": [
                        {"region": "East", "total": 120},
                        {"region": "West", "total": 80},
                    ],
                    "row_count": 2,
                    "truncated": False,
                },
                duration_ms=24,
            ),
        )
        await asyncio.sleep(0.15)
        yield RuntimeEvent(
            type=RuntimeEventType.STEP,
            step=_preview_step(
                step=3,
                thought="将聚合结果整理为可渲染图表。",
                tool_name="plot_chart",
                arguments={
                    "spec": {
                        "type": "bar",
                        "title": "区域销售额",
                        "x_field": "region",
                        "y_fields": ["total"],
                        "data": [
                            {"region": "East", "total": 120},
                            {"region": "West", "total": 80},
                        ],
                    }
                },
                result={
                    "kind": "chart",
                    "spec": {
                        "type": "bar",
                        "title": "区域销售额",
                        "x_field": "region",
                        "y_fields": ["total"],
                        "data": [
                            {"region": "East", "total": 120},
                            {"region": "West", "total": 80},
                        ],
                    },
                },
                duration_ms=6,
            ),
        )
        yield RuntimeEvent(
            type=RuntimeEventType.TEXT,
            text=(f"当前未配置真实模型，以上为界面预览轨迹。收到的问题：{question}。"),
        )
        yield RuntimeEvent(type=RuntimeEventType.DONE, data={"status": "completed"})


def build_chat_runtime(
    settings: Settings,
    *,
    model_router: ModelRouter | None = None,
    tool_registry: ToolRegistry | None = None,
) -> ChatRuntime:
    if settings.chat_runtime_mode == "preview":
        return PreviewChatRuntime()
    if (
        settings.chat_runtime_mode == "agent"
        and model_router is not None
        and tool_registry is not None
    ):
        return AgentChatRuntime(
            Agent(
                model=model_router,
                tools=tool_registry,
                config=AgentConfig(
                    max_steps=settings.agent_max_steps,
                    max_total_tokens=settings.agent_max_total_tokens,
                    max_tool_calls_per_step=settings.agent_max_tool_calls_per_step,
                    max_tool_budget_retries=settings.agent_max_tool_budget_retries,
                    max_parallel_tools=settings.agent_max_parallel_tools,
                    context_char_budget=settings.agent_context_char_budget,
                    keep_recent_tool_results=settings.agent_keep_recent_tool_results,
                    parallel_tool_calls=settings.agent_parallel_tools,
                    stream_model=True,
                ),
            )
        )
    return UnavailableChatRuntime()


def _preview_step(
    *,
    step: int,
    thought: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    duration_ms: float,
) -> AgentStep:
    return AgentStep(
        step=step,
        assistant_content=thought,
        tool_calls=[
            {
                "id": f"preview-call-{step}",
                "name": tool_name,
                "arguments": arguments,
            }
        ],
        tool_executions=[
            ToolExecution(
                tool_call_id=f"preview-call-{step}",
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                duration_ms=duration_ms,
            )
        ],
        usage=TokenUsage(input_tokens=0, output_tokens=0),
    )


def _agent_system_prompt() -> str:
    return (
        "你是 DataPilot 对话式数据分析智能体。"
        "本地分析数据与公司 MCP 数据是两个独立数据源。"
        "本地数据：先使用 list_tables 和 get_schema 了解表结构，"
        "再用 run_sql 执行只读 SELECT。"
        "公司 MCP 数据：先使用 mcp__get_company_schema，"
        "再使用 mcp__query_company_data；禁止查询 information_schema。"
        "需要图表时使用 plot_chart，并传入结构化 Chart Spec。"
        "禁止生成写操作或访问未登记数据源。"
        "每轮工具调用优先控制在 3 个以内，按关键维度分批分析。"
        "工具失败后必须根据错误修正参数或更换工具，"
        "禁止重复提交完全相同的工具调用。"
        "调用工具时不要输出面向用户的结论；获得足够信息后再简洁回答。"
    )
