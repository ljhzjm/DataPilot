from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agent.models import AgentStep, ChatMessage, ToolCall
from app.chat.schemas import (
    ConversationDetail,
    ConversationSummary,
    MessageRole,
    MessageStatus,
    MessageView,
)
from app.db.models import AgentStepRecord, Conversation, Message, utc_now


class ConversationStore(Protocol):
    async def create_conversation(self, title: str = "新会话") -> ConversationDetail: ...

    async def list_conversations(self) -> list[ConversationSummary]: ...

    async def get_conversation(self, conversation_id: UUID) -> ConversationDetail | None: ...

    async def append_message(
        self,
        conversation_id: UUID,
        *,
        role: MessageRole,
        content: str | None,
        status: MessageStatus = "completed",
        tool_calls: list[dict[str, Any]] | None = None,
        request_id: UUID | None = None,
    ) -> MessageView: ...

    async def complete_assistant_message(
        self,
        message_id: UUID,
        *,
        content: str | None,
        status: MessageStatus,
        steps: Sequence[AgentStep],
    ) -> MessageView: ...

    async def get_history(
        self,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> list[ChatMessage]: ...

    async def get_assistant_by_request_id(
        self,
        conversation_id: UUID,
        request_id: UUID,
    ) -> MessageView | None: ...

    async def get_message(self, message_id: UUID) -> MessageView | None: ...


class ConversationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_conversation(self, title: str = "新会话") -> ConversationDetail:
        async with self._session_factory() as session:
            conversation = Conversation(title=title)
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            return _conversation_detail(conversation, [])

    async def list_conversations(self) -> list[ConversationSummary]:
        statement = (
            select(Conversation, func.count(Message.id))
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .group_by(Conversation.id)
            .order_by(desc(Conversation.updated_at))
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [
            ConversationSummary(
                id=conversation.id,
                title=conversation.title,
                message_count=int(message_count),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation, message_count in rows
        ]

    async def get_conversation(self, conversation_id: UUID) -> ConversationDetail | None:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.steps))
            .where(Conversation.id == conversation_id)
        )
        async with self._session_factory() as session:
            conversation = (await session.execute(statement)).scalar_one_or_none()
            if conversation is None:
                return None
            messages = [_message_view(message) for message in conversation.messages]
            return _conversation_detail(conversation, messages)

    async def append_message(
        self,
        conversation_id: UUID,
        *,
        role: MessageRole,
        content: str | None,
        status: MessageStatus = "completed",
        tool_calls: list[dict[str, Any]] | None = None,
        request_id: UUID | None = None,
    ) -> MessageView:
        async with self._session_factory() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                raise KeyError(f"Conversation not found: {conversation_id}")

            next_sequence = (
                await session.scalar(
                    select(func.coalesce(func.max(Message.sequence), 0)).where(
                        Message.conversation_id == conversation_id
                    )
                )
                or 0
            ) + 1
            message = Message(
                conversation_id=conversation_id,
                sequence=next_sequence,
                role=role,
                content=content,
                status=status,
                tool_calls=tool_calls or [],
                request_id=request_id,
            )
            if role == "user" and conversation.title == "新会话" and content:
                conversation.title = content.strip()[:40]
            conversation.updated_at = utc_now()
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
                created_at=message.created_at,
            )

    async def complete_assistant_message(
        self,
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
                    .where(Message.id == message_id)
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

            conversation = await session.get(Conversation, message.conversation_id)
            if conversation is not None:
                conversation.updated_at = utc_now()
            await session.commit()
            return _message_view(message)

    async def get_history(
        self,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> list[ChatMessage]:
        conversation = await self.get_conversation(conversation_id)
        if conversation is None:
            return []

        history: list[ChatMessage] = []
        for message in conversation.messages[-limit:]:
            if message.role not in {"user", "assistant"}:
                continue
            history.append(
                ChatMessage(
                    role=message.role,
                    content=message.content,
                    tool_calls=[
                        ToolCall.model_validate(tool_call) for tool_call in message.tool_calls
                    ],
                )
            )
        return history

    async def get_assistant_by_request_id(
        self,
        conversation_id: UUID,
        request_id: UUID,
    ) -> MessageView | None:
        statement = (
            select(Message)
            .options(selectinload(Message.steps))
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
                Message.request_id == request_id,
            )
        )
        async with self._session_factory() as session:
            message = (await session.execute(statement)).scalar_one_or_none()
            return _message_view(message) if message is not None else None

    async def get_message(self, message_id: UUID) -> MessageView | None:
        statement = (
            select(Message).options(selectinload(Message.steps)).where(Message.id == message_id)
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
        created_at=message.created_at,
    )
