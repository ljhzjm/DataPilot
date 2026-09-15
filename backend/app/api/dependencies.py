from typing import cast

from fastapi import Request

from app.chat.runtime import ChatRuntime
from app.chat.service import ConversationService
from app.db.session import AsyncSessionLocal


def get_conversation_service() -> ConversationService:
    return ConversationService(AsyncSessionLocal)


def get_chat_runtime(request: Request) -> ChatRuntime:
    return cast(ChatRuntime, request.app.state.chat_runtime)
