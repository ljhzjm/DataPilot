from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.agent.models import AgentStep, ChatMessage, TokenUsage, ToolCall
from app.api.dependencies import (
    get_chat_runtime,
    get_chat_task_manager,
    get_conversation_service,
    get_event_broker,
)
from app.chat.events import InMemoryEventBroker
from app.chat.runtime import RuntimeEvent, RuntimeEventType
from app.chat.schemas import (
    ConversationDetail,
    ConversationPage,
    ConversationSummary,
    MessageRole,
    MessageStatus,
    MessageView,
)
from app.chat.tasks import ChatTaskManager
from app.main import app


class FakeStore:
    def __init__(self) -> None:
        self.conversations: dict[UUID, ConversationDetail] = {}

    async def create_conversation(self, title: str = "新会话") -> ConversationDetail:
        now = datetime.now(UTC)
        conversation = ConversationDetail(
            id=uuid4(),
            title=title,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self.conversations[conversation.id] = conversation
        return conversation

    async def list_conversations(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        query: str | None = None,
        include_archived: bool = False,
    ) -> ConversationPage:
        del query, include_archived
        items = [
            ConversationSummary(
                id=conversation.id,
                title=conversation.title,
                message_count=len(conversation.messages),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation in self.conversations.values()
        ]
        return ConversationPage(
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
        )

    async def get_conversation(self, conversation_id: UUID) -> ConversationDetail | None:
        return self.conversations.get(conversation_id)

    async def append_message(
        self,
        conversation_id: UUID,
        *,
        role: MessageRole,
        content: str | None,
        status: MessageStatus = "completed",
        tool_calls: list[dict[str, object]] | None = None,
        request_id: UUID | None = None,
    ) -> MessageView:
        conversation = self.conversations[conversation_id]
        message = MessageView(
            id=uuid4(),
            role=role,
            content=content,
            status=status,
            tool_calls=tool_calls or [],
            steps=[],
            request_id=request_id,
            created_at=datetime.now(UTC),
        )
        conversation.messages.append(message)
        return message

    async def complete_assistant_message(
        self,
        message_id: UUID,
        *,
        content: str | None,
        status: MessageStatus,
        steps: Sequence[AgentStep],
    ) -> MessageView:
        for conversation in self.conversations.values():
            for message in conversation.messages:
                if message.id == message_id:
                    message.content = content
                    message.status = status
                    message.steps = list(steps)
                    return message
        raise KeyError(message_id)

    async def get_history(
        self,
        conversation_id: UUID,
        *,
        limit: int,
    ) -> list[ChatMessage]:
        conversation = self.conversations[conversation_id]
        return [
            ChatMessage(role=message.role, content=message.content)
            for message in conversation.messages[-limit:]
            if message.role in {"user", "assistant"}
        ]

    async def get_assistant_by_request_id(
        self,
        conversation_id: UUID,
        request_id: UUID,
    ) -> MessageView | None:
        conversation = self.conversations[conversation_id]
        for message in conversation.messages:
            if message.role == "assistant" and message.request_id == request_id:
                return message
        return None

    async def get_message(self, message_id: UUID) -> MessageView | None:
        for conversation in self.conversations.values():
            for message in conversation.messages:
                if message.id == message_id:
                    return message
        return None

    async def archive_conversation(
        self,
        conversation_id: UUID,
        *,
        archived: bool,
    ) -> bool:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            return False
        conversation.updated_at = datetime.now(UTC)
        return True

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        return self.conversations.pop(conversation_id, None) is not None


class FakeRuntime:
    async def stream(
        self,
        *,
        question: str,
        history: Sequence[ChatMessage],
    ) -> AsyncIterator[RuntimeEvent]:
        del history
        yield RuntimeEvent(
            type=RuntimeEventType.STEP,
            step=AgentStep(
                step=1,
                assistant_content=f"分析问题：{question}",
                tool_calls=[ToolCall(id="call-1", name="list_tables", arguments={})],
                usage=TokenUsage(input_tokens=3, output_tokens=1),
            ),
        )
        yield RuntimeEvent(type=RuntimeEventType.TEXT, text="分析完成")
        yield RuntimeEvent(type=RuntimeEventType.DONE, data={"status": "completed"})


def test_stream_message_persists_messages_and_steps() -> None:
    store = FakeStore()
    broker = InMemoryEventBroker()
    task_manager = ChatTaskManager()
    app.dependency_overrides[get_conversation_service] = lambda: store
    app.dependency_overrides[get_chat_runtime] = lambda: FakeRuntime()
    app.dependency_overrides[get_event_broker] = lambda: broker
    app.dependency_overrides[get_chat_task_manager] = lambda: task_manager

    try:
        with TestClient(app) as client:
            create_response = client.post("/api/conversations")
            assert create_response.status_code == 201
            conversation_id = create_response.json()["id"]

            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/messages/stream",
                json={"content": "各区域销售额是多少？"},
            ) as stream_response:
                body = "".join(stream_response.iter_text())

            detail_response = client.get(f"/api/conversations/{conversation_id}")

        assert stream_response.status_code == 200
        assert "event: start" in body
        assert "event: step" in body
        assert "event: text" in body
        assert "event: done" in body
        detail = detail_response.json()
        assert [message["role"] for message in detail["messages"]] == [
            "user",
            "assistant",
        ]
        assert detail["messages"][1]["content"] == "分析完成"
        assert detail["messages"][1]["steps"][0]["tool_calls"][0]["name"] == "list_tables"
    finally:
        app.dependency_overrides.clear()


def test_stream_message_is_idempotent_for_same_client_request_id() -> None:
    store = FakeStore()
    broker = InMemoryEventBroker()
    task_manager = ChatTaskManager()
    app.dependency_overrides[get_conversation_service] = lambda: store
    app.dependency_overrides[get_chat_runtime] = lambda: FakeRuntime()
    app.dependency_overrides[get_event_broker] = lambda: broker
    app.dependency_overrides[get_chat_task_manager] = lambda: task_manager
    request_id = str(uuid4())

    try:
        with TestClient(app) as client:
            conversation_id = client.post("/api/conversations").json()["id"]
            payload = {
                "content": "统计销售额",
                "client_request_id": request_id,
            }
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/messages/stream",
                json=payload,
            ) as first:
                first_body = "".join(first.iter_text())
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/messages/stream",
                json=payload,
            ) as second:
                second_body = "".join(second.iter_text())
            detail = client.get(f"/api/conversations/{conversation_id}").json()

        assert "event: done" in first_body
        assert "event: done" in second_body
        assert len(detail["messages"]) == 2
    finally:
        app.dependency_overrides.clear()
