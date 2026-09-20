from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agent.models import AgentStep
from app.chat.schemas import MessageView
from app.db.models import AgentStepRecord, Conversation, LLMUsageRecord, Message
from app.observability.schemas import (
    ToolMetrics,
    TraceView,
    UsagePage,
    UsageRecordView,
    UsageSummary,
)


class ObservabilityService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def summary(
        self,
        *,
        workspace_id: UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        conversation_id: UUID | None = None,
    ) -> UsageSummary:
        filters = _usage_filters(
            workspace_id=workspace_id,
            start_at=start_at,
            end_at=end_at,
            conversation_id=conversation_id,
        )
        statement = select(
            func.count(LLMUsageRecord.id),
            func.coalesce(func.sum(LLMUsageRecord.input_tokens), 0),
            func.coalesce(func.sum(LLMUsageRecord.output_tokens), 0),
            func.coalesce(func.sum(LLMUsageRecord.estimated_cost_usd), 0),
            func.coalesce(func.avg(LLMUsageRecord.latency_ms), 0),
            func.coalesce(
                func.sum(
                    case(
                        (LLMUsageRecord.success.is_(False), 1),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*filters)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one()
        input_tokens = int(row[1])
        output_tokens = int(row[2])
        return UsageSummary(
            call_count=int(row[0]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            estimated_cost_usd=float(row[3] or 0),
            average_latency_ms=float(row[4] or 0),
            error_count=int(row[5] or 0),
        )

    async def list_usage(
        self,
        *,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        conversation_id: UUID | None = None,
    ) -> UsagePage:
        filters = _usage_filters(
            workspace_id=workspace_id,
            start_at=start_at,
            end_at=end_at,
            conversation_id=conversation_id,
        )
        statement = (
            select(LLMUsageRecord)
            .where(*filters)
            .order_by(LLMUsageRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count(LLMUsageRecord.id)).where(*filters)
        async with self._session_factory() as session:
            records = list((await session.scalars(statement)).all())
            total = int(await session.scalar(count_statement) or 0)
        return UsagePage(
            items=[_usage_view(record) for record in records],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_trace(
        self,
        workspace_id: UUID,
        trace_id: UUID,
    ) -> TraceView | None:
        message_statement = (
            select(Message)
            .options(selectinload(Message.steps))
            .join(Conversation)
            .where(
                Message.trace_id == trace_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        usage_statement = (
            select(LLMUsageRecord)
            .where(
                LLMUsageRecord.trace_id == trace_id,
                LLMUsageRecord.workspace_id == workspace_id,
            )
            .order_by(LLMUsageRecord.created_at)
        )
        async with self._session_factory() as session:
            message = (await session.execute(message_statement)).scalar_one_or_none()
            usage_records = list((await session.scalars(usage_statement)).all())

        if message is None and not usage_records:
            return None

        steps = [
            step
            for step_record in (message.steps if message is not None else [])
            for step in _steps_from_record(step_record)
        ]
        executions = [execution for step in steps for execution in step.tool_executions]
        tool_metrics = ToolMetrics(
            call_count=len(executions),
            failed_call_count=sum(1 for execution in executions if execution.error),
            total_duration_ms=sum(execution.duration_ms for execution in executions),
        )
        return TraceView(
            trace_id=trace_id,
            conversation_id=message.conversation_id if message is not None else None,
            assistant_message=_message_view(message) if message is not None else None,
            usage_records=[_usage_view(record) for record in usage_records],
            tool_metrics=tool_metrics,
        )


def _usage_filters(
    *,
    workspace_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    conversation_id: UUID | None,
) -> list[Any]:
    filters: list[Any] = [LLMUsageRecord.workspace_id == workspace_id]
    if start_at is not None:
        filters.append(LLMUsageRecord.created_at >= start_at)
    if end_at is not None:
        filters.append(LLMUsageRecord.created_at <= end_at)
    if conversation_id is not None:
        filters.append(LLMUsageRecord.conversation_id == conversation_id)
    return filters


def _usage_view(record: LLMUsageRecord) -> UsageRecordView:
    return UsageRecordView(
        id=record.id,
        request_id=record.request_id,
        trace_id=record.trace_id,
        conversation_id=record.conversation_id,
        message_id=record.message_id,
        task=record.task,
        provider=record.provider,
        model=record.model,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        estimated_cost_usd=float(record.estimated_cost_usd or 0),
        latency_ms=record.latency_ms,
        success=record.success,
        error_type=record.error_type,
        created_at=record.created_at,
    )


def _message_view(message: Message) -> MessageView:
    from app.chat.service import _message_view as chat_message_view

    return chat_message_view(message)


def _steps_from_record(record: AgentStepRecord) -> list[AgentStep]:
    return [
        AgentStep(
            step=record.step_index,
            assistant_content=record.assistant_content,
            tool_calls=record.tool_calls,
            tool_executions=record.tool_executions,
            usage=record.usage,
        )
    ]
