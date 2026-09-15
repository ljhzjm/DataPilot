from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.agent.models import AgentStep, ChatMessage, TokenUsage, ToolCall
from app.api.dependencies import get_chat_runtime, get_conversation_service
from app.chat.runtime import RuntimeEvent, RuntimeEventType
from app.chat.schemas import (
    ConversationDetail,
    ConversationSummary,
    MessageRole,
    MessageStatus,
    MessageView,
)
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

    async def list_conversations(self) -> list[ConversationSummary]:
        return [
            ConversationSummary(
                id=conversation.id,
                title=conversation.title,
                message_count=len(conversation.messages),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation in self.conversations.values()
        ]

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
    ) -> MessageView:
        conversation = self.conversations[conversation_id]
        message = MessageView(
            id=uuid4(),
            role=role,
            content=content,
            status=status,
            tool_calls=tool_calls or [],
            steps=[],
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
    app.dependency_overrides[get_conversation_service] = lambda: store
    app.dependency_overrides[get_chat_runtime] = lambda: FakeRuntime()

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
