import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    get_chat_runtime,
    get_chat_task_manager,
    get_conversation_service,
    get_event_broker,
)
from app.chat.events import BrokerEvent, EventBroker
from app.chat.runtime import ChatRuntime
from app.chat.schemas import (
    ConversationDetail,
    ConversationSummary,
    MessageCreate,
    MessageView,
)
from app.chat.service import ConversationStore
from app.chat.sse import encode_sse_data
from app.chat.tasks import ChatTaskManager
from app.chat.worker import ChatWorker
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
    broker: Annotated[EventBroker, Depends(get_event_broker)],
    task_manager: Annotated[ChatTaskManager, Depends(get_chat_task_manager)],
) -> StreamingResponse:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    settings = get_settings()
    request_id = payload.client_request_id or uuid4()
    assistant_message = await store.get_assistant_by_request_id(
        conversation_id,
        request_id,
    )

    if assistant_message is None:
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
            request_id=request_id,
        )
        worker = ChatWorker(store=store, runtime=runtime, broker=broker)
        task_manager.start(
            assistant_message.id,
            worker.run(
                assistant_message_id=assistant_message.id,
                conversation_id=conversation_id,
                request_id=request_id,
                question=payload.content,
                history=history,
            ),
        )
    elif assistant_message.status == "streaming" and not task_manager.is_running(
        assistant_message.id
    ):
        assistant_message = await store.complete_assistant_message(
            assistant_message.id,
            content=assistant_message.content,
            status="error",
            steps=assistant_message.steps,
        )

    last_event_id = request.headers.get("Last-Event-ID") or "0-0"

    async def event_stream() -> AsyncIterator[str]:
        initial_events = await broker.read(
            assistant_message.id,
            last_event_id=last_event_id,
            block_ms=0,
        )
        if not initial_events and not task_manager.is_running(assistant_message.id):
            async for frame in _snapshot_stream(
                assistant_message,
                conversation_id=conversation_id,
            ):
                yield frame
            return

        cursor = last_event_id
        buffered = initial_events
        while True:
            if await request.is_disconnected():
                return

            if buffered:
                events = buffered
                buffered = []
            else:
                events = await broker.read(
                    assistant_message.id,
                    last_event_id=cursor,
                    block_ms=15_000,
                )

            if not events:
                await asyncio.sleep(0.02)
                yield ": ping\n\n"
                continue

            for event in events:
                cursor = event.id
                yield _encode_broker_event(event)
                if event.event in {"done", "error", "aborted"}:
                    return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/abort",
    status_code=status.HTTP_202_ACCEPTED,
)
async def abort_message(
    conversation_id: UUID,
    message_id: UUID,
    store: Annotated[ConversationStore, Depends(get_conversation_service)],
    task_manager: Annotated[ChatTaskManager, Depends(get_chat_task_manager)],
) -> dict[str, bool]:
    if task_manager.abort(message_id):
        return {"aborted": True}

    message = await store.get_message(message_id)
    if message is not None and message.role == "assistant" and message.status == "streaming":
        await store.complete_assistant_message(
            message_id,
            content=message.content,
            status="aborted",
            steps=message.steps,
        )
        return {"aborted": True}
    return {"aborted": False}


def _encode_broker_event(event: BrokerEvent) -> str:
    return encode_sse_data(
        event.event,
        event.data,
        event_id=event.id,
    )


async def _snapshot_stream(
    message: MessageView,
    *,
    conversation_id: UUID,
) -> AsyncIterator[str]:
    start_data = {
        "conversation_id": str(conversation_id),
        "assistant_message_id": str(message.id),
        "snapshot": True,
    }
    yield encode_sse_data("start", start_data, event_id="snapshot-start")
    for step in message.steps:
        payload = {
            "type": "step",
            "step": step.model_dump(mode="json"),
            "text": None,
            "message": None,
            "data": {},
        }
        yield encode_sse_data(
            "step",
            payload,
            event_id=f"snapshot-step-{step.step}",
        )
    if message.content:
        yield encode_sse_data(
            "text",
            {
                "type": "text",
                "step": None,
                "text": message.content,
                "message": None,
                "data": {},
            },
            event_id="snapshot-text",
        )
    terminal: str = message.status
    if terminal == "completed":
        terminal = "done"
    yield encode_sse_data(
        terminal,
        {
            "assistant_message_id": str(message.id),
            "persisted": True,
            "snapshot": True,
        },
        event_id=f"snapshot-{terminal}",
    )
