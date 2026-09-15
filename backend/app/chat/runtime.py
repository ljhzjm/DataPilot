import asyncio
from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.agent.loop import Agent
from app.agent.models import AgentStep, ChatMessage, TokenUsage, ToolExecution
from app.core.config import Settings


class RuntimeEventType(StrEnum):
    STEP = "step"
    TEXT = "text"
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
    ) -> AsyncIterator[RuntimeEvent]: ...


class AgentChatRuntime:
    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    async def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
    ) -> AsyncIterator[RuntimeEvent]:
        del history
        result = await self._agent.run(question)
        for step in result.steps:
            yield RuntimeEvent(type=RuntimeEventType.STEP, step=step)
        if result.output:
            yield RuntimeEvent(type=RuntimeEventType.TEXT, text=result.output)
        yield RuntimeEvent(
            type=RuntimeEventType.DONE,
            data={
                "status": result.status,
                "termination_reason": result.termination_reason,
            },
        )


class UnavailableChatRuntime:
    async def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
    ) -> AsyncIterator[RuntimeEvent]:
        del question, history
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
    ) -> AsyncIterator[RuntimeEvent]:
        del history
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


def build_chat_runtime(settings: Settings) -> ChatRuntime:
    if settings.chat_runtime_mode == "preview":
        return PreviewChatRuntime()
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
