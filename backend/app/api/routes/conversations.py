import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.agent.models import AgentStep
from app.api.dependencies import get_chat_runtime, get_conversation_service
from app.chat.runtime import ChatRuntime, RuntimeEventType
from app.chat.schemas import (
    ConversationDetail,
    ConversationSummary,
    MessageCreate,
    MessageStatus,
)
from app.chat.service import ConversationStore
from app.chat.sse import encode_sse, encode_sse_data
from app.core.config import get_settings

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    store: Annotated[ConversationStore, Depends(get_conversation_service)],
) -> ConversationDetail:
    return await store.create_conversation()


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    store: Annotated[ConversationStore, Depends(get_conversation_service)],
) -> list[ConversationSummary]:
    return await store.list_conversations()


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    store: Annotated[ConversationStore, Depends(get_conversation_service)],
) -> ConversationDetail:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.post("/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: UUID,
    payload: MessageCreate,
    request: Request,
    store: Annotated[ConversationStore, Depends(get_conversation_service)],
    runtime: Annotated[ChatRuntime, Depends(get_chat_runtime)],
) -> StreamingResponse:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    settings = get_settings()
    history = await store.get_history(
        conversation_id,
        limit=settings.chat_history_limit,
    )
    await store.append_message(
        conversation_id,
        role="user",
        content=payload.content,
    )
    assistant_message = await store.append_message(
        conversation_id,
        role="assistant",
        content="",
        status="streaming",
    )

    async def event_stream() -> AsyncIterator[str]:
        accumulated_text = ""
        steps: list[AgentStep] = []
        message_status: MessageStatus = "completed"
        error_message: str | None = None
        persisted = False

        yield encode_sse_data(
            "start",
            {
                "conversation_id": str(conversation_id),
                "assistant_message_id": str(assistant_message.id),
            },
        )

        try:
            async for event in runtime.stream(question=payload.content, history=history):
                if await request.is_disconnected():
                    message_status = "aborted"
                    break

                if event.type is RuntimeEventType.STEP and event.step is not None:
                    steps.append(event.step)
                    yield encode_sse(event)
                elif event.type is RuntimeEventType.TEXT and event.text:
                    accumulated_text += event.text
                    yield encode_sse(event)
                elif event.type is RuntimeEventType.ERROR:
                    message_status = "error"
                    error_message = event.message or "Agent execution failed."
                    yield encode_sse(event)
                    break
                elif event.type is RuntimeEventType.DONE:
                    break
        except asyncio.CancelledError:
            message_status = "aborted"
            raise
        except Exception as exc:
            message_status = "error"
            error_message = f"{type(exc).__name__}: {exc}"
            yield encode_sse_data("error", {"message": error_message})
        finally:
            try:
                await asyncio.shield(
                    store.complete_assistant_message(
                        assistant_message.id,
                        content=accumulated_text,
                        status=message_status,
                        steps=steps,
                    )
                )
                persisted = True
            except Exception:
                persisted = False

        if message_status == "aborted":
            yield encode_sse_data(
                "aborted",
                {
                    "assistant_message_id": str(assistant_message.id),
                    "persisted": persisted,
                },
            )
        elif message_status == "completed":
            yield encode_sse_data(
                "done",
                {
                    "conversation_id": str(conversation_id),
                    "assistant_message_id": str(assistant_message.id),
                    "persisted": persisted,
                },
            )
        elif error_message:
            yield encode_sse_data(
                "error",
                {
                    "message": error_message,
                    "assistant_message_id": str(assistant_message.id),
                    "persisted": persisted,
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
