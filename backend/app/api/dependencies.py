from typing import cast

from fastapi import Request

from app.chat.events import EventBroker
from app.chat.runtime import ChatRuntime
from app.chat.service import ConversationService
from app.chat.tasks import ChatTaskManager
from app.db.session import AsyncSessionLocal


def get_conversation_service() -> ConversationService:
    return ConversationService(AsyncSessionLocal)


def get_chat_runtime(request: Request) -> ChatRuntime:
    return cast(ChatRuntime, request.app.state.chat_runtime)


def get_event_broker(request: Request) -> EventBroker:
    return cast(EventBroker, request.app.state.chat_event_broker)


def get_chat_task_manager(request: Request) -> ChatTaskManager:
    return cast(ChatTaskManager, request.app.state.chat_task_manager)
