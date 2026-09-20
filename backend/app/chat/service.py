from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agent.models import AgentStep, ChatMessage
from app.chat.schemas import (
    ConversationDetail,
    ConversationPage,
    ConversationSummary,
    MessageRole,
    MessageStatus,
    MessageView,
)
from app.db.models import AgentStepRecord, Conversation, Message, utc_now


class ConversationStore(Protocol):
    async def create_conversation(
        self,
        workspace_id: UUID,
        title: str = "新会话",
    ) -> ConversationDetail: ...

    async def list_conversations(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        query: str | None = None,
        include_archived: bool = False,
    ) -> ConversationPage: ...

    async def get_conversation(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
    ) -> ConversationDetail | None: ...

    async def append_message(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        *,
        role: MessageRole,
        content: str | None,
        status: MessageStatus = "completed",
        tool_calls: list[dict[str, Any]] | None = None,
        request_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> MessageView: ...

    async def complete_assistant_message(
        self,
        workspace_id: UUID,
        message_id: UUID,
        *,
        content: str | None,
        status: MessageStatus,
        steps: Sequence[AgentStep],
    ) -> MessageView: ...

    async def get_history(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> list[ChatMessage]: ...

    async def get_assistant_by_request_id(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        request_id: UUID,
    ) -> MessageView | None: ...

    async def get_message(
        self,
        workspace_id: UUID,
        message_id: UUID,
    ) -> MessageView | None: ...

    async def archive_conversation(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        *,
        archived: bool,
    ) -> bool: ...

    async def delete_conversation(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
    ) -> bool: ...


class ConversationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        history_char_budget: int = 12_000,
    ) -> None:
        self._session_factory = session_factory
        self._history_char_budget = history_char_budget

    async def create_conversation(
        self,
        workspace_id: UUID,
        title: str = "新会话",
    ) -> ConversationDetail:
        async with self._session_factory() as session:
            conversation = Conversation(
                workspace_id=workspace_id,
                title=title,
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            return _conversation_detail(conversation, [])

    async def list_conversations(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        query: str | None = None,
        include_archived: bool = False,
    ) -> ConversationPage:
        filters = [Conversation.workspace_id == workspace_id]
        if not include_archived:
            filters.append(Conversation.archived_at.is_(None))
        if query:
            filters.append(Conversation.title.ilike(f"%{query.strip()}%"))

        count_statement = select(func.count(Conversation.id)).where(*filters)
        message_count = (
            select(func.count(Message.id))
            .where(Message.conversation_id == Conversation.id)
            .correlate(Conversation)
            .scalar_subquery()
        )
        statement = (
            select(Conversation, message_count.label("message_count"))
            .where(*filters)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
            total = int(await session.scalar(count_statement) or 0)
        return ConversationPage(
            items=[
                ConversationSummary(
                    id=conversation.id,
                    title=conversation.title,
                    message_count=int(message_count_value),
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                    archived_at=conversation.archived_at,
                )
                for conversation, message_count_value in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_conversation(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
    ) -> ConversationDetail | None:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.steps))
            .where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        async with self._session_factory() as session:
            conversation = (await session.execute(statement)).scalar_one_or_none()
            if conversation is None:
                return None
            messages = [_message_view(message) for message in conversation.messages]
            return _conversation_detail(conversation, messages)

    async def append_message(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        *,
        role: MessageRole,
        content: str | None,
        status: MessageStatus = "completed",
        tool_calls: list[dict[str, Any]] | None = None,
        request_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> MessageView:
        async with self._session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
            if conversation is None:
                raise KeyError(f"Conversation not found: {conversation_id}")

            allocated_sequence = await session.scalar(
                update(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.workspace_id == workspace_id,
                )
                .values(
                    next_sequence=Conversation.next_sequence + 1,
                    updated_at=utc_now(),
                )
                .returning(Conversation.next_sequence)
            )
            if allocated_sequence is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            message = Message(
                conversation_id=conversation_id,
                sequence=int(allocated_sequence) - 1,
                role=role,
                content=content,
                status=status,
                tool_calls=tool_calls or [],
                request_id=request_id,
                trace_id=trace_id,
            )
            if role == "user" and conversation.title == "新会话" and content:
                conversation.title = content.strip()[:40]
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return MessageView(
                id=message.id,
                role=message.role,
                content=message.content,
                status=message.status,
                tool_calls=message.tool_calls,
                steps=[],
                request_id=message.request_id,
                trace_id=message.trace_id,
                created_at=message.created_at,
            )

    async def complete_assistant_message(
        self,
        workspace_id: UUID,
        message_id: UUID,
        *,
        content: str | None,
        status: MessageStatus,
        steps: Sequence[AgentStep],
    ) -> MessageView:
        async with self._session_factory() as session:
            message = (
                await session.execute(
                    select(Message)
                    .options(selectinload(Message.steps))
                    .join(Conversation)
                    .where(
                        Message.id == message_id,
                        Conversation.workspace_id == workspace_id,
                    )
                )
            ).scalar_one_or_none()
            if message is None:
                raise KeyError(f"Message not found: {message_id}")

            message.content = content
            message.status = status
            message.steps.clear()
            for step in steps:
                payload = step.model_dump(mode="json")
                message.steps.append(
                    AgentStepRecord(
                        message_id=message_id,
                        step_index=step.step,
                        assistant_content=step.assistant_content,
                        tool_calls=payload["tool_calls"],
                        tool_executions=payload["tool_executions"],
                        usage=payload["usage"],
                    )
                )

            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == message.conversation_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
            if conversation is not None:
                conversation.updated_at = utc_now()
            await session.commit()
            return _message_view(message)

    async def get_history(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> list[ChatMessage]:
        conversation = await self.get_conversation(workspace_id, conversation_id)
        if conversation is None:
            return []

        selected: list[ChatMessage] = []
        remaining = self._history_char_budget
        for message in reversed(conversation.messages[-limit:]):
            if message.role not in {"user", "assistant"}:
                continue
            content = _history_content(message)
            if not content:
                continue
            content = content[:remaining]
            if not content:
                break
            selected.append(ChatMessage(role=message.role, content=content))
            remaining -= len(content)
            if remaining <= 0:
                break
        selected.reverse()
        return selected

    async def archive_conversation(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        *,
        archived: bool,
    ) -> bool:
        async with self._session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
            if conversation is None:
                return False
            conversation.archived_at = utc_now() if archived else None
            conversation.updated_at = utc_now()
            await session.commit()
            return True

    async def delete_conversation(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
    ) -> bool:
        async with self._session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
            if conversation is None:
                return False
            await session.delete(conversation)
            await session.commit()
            return True

    async def get_assistant_by_request_id(
        self,
        workspace_id: UUID,
        conversation_id: UUID,
        request_id: UUID,
    ) -> MessageView | None:
        statement = (
            select(Message)
            .options(selectinload(Message.steps))
            .join(Conversation)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
                Message.request_id == request_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        async with self._session_factory() as session:
            message = (await session.execute(statement)).scalar_one_or_none()
            return _message_view(message) if message is not None else None

    async def get_message(
        self,
        workspace_id: UUID,
        message_id: UUID,
    ) -> MessageView | None:
        statement = (
            select(Message)
            .options(selectinload(Message.steps))
            .join(Conversation)
            .where(
                Message.id == message_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        async with self._session_factory() as session:
            message = (await session.execute(statement)).scalar_one_or_none()
            return _message_view(message) if message is not None else None


def _conversation_detail(
    conversation: Conversation,
    messages: list[MessageView],
) -> ConversationDetail:
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        messages=messages,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_view(message: Message) -> MessageView:
    return MessageView(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        tool_calls=message.tool_calls,
        steps=[
            AgentStep(
                step=step.step_index,
                assistant_content=step.assistant_content,
                tool_calls=step.tool_calls,
                tool_executions=step.tool_executions,
                usage=step.usage,
            )
            for step in message.steps
        ],
        request_id=message.request_id,
        trace_id=message.trace_id,
        created_at=message.created_at,
    )


def _history_content(message: MessageView) -> str:
    parts: list[str] = []
    if message.content:
        parts.append(message.content)
    if message.steps:
        summaries = [_history_step_summary(step) for step in message.steps if step.tool_executions]
        if summaries:
            parts.append("历史工具执行摘要：\n" + "\n".join(summaries))
    return "\n\n".join(parts)[:6000]


def _history_step_summary(step: AgentStep) -> str:
    executions = []
    for execution in step.tool_executions:
        result = execution.result if isinstance(execution.result, dict) else {}
        if "rows" in result:
            detail = f"columns={result.get('columns')}, row_count={result.get('row_count')}"
        elif "table_name" in result:
            detail = f"table={result.get('table_name')}"
        elif result.get("kind") == "chart":
            detail = "chart_rendered=true"
        elif execution.error:
            detail = f"error={execution.error[:200]}"
        else:
            detail = "result=available"
        executions.append(f"{execution.tool_name}: {detail}")
    return f"- step {step.step}: " + "; ".join(executions)
