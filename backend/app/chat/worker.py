import asyncio
from collections.abc import Sequence
from uuid import UUID

from app.agent.models import AgentStep, ChatMessage
from app.chat.events import EventBroker
from app.chat.runtime import ChatRuntime, RuntimeEventType
from app.chat.schemas import MessageStatus
from app.chat.service import ConversationStore


class ChatWorker:
    def __init__(
        self,
        *,
        store: ConversationStore,
        runtime: ChatRuntime,
        broker: EventBroker,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._broker = broker

    async def run(
        self,
        *,
        assistant_message_id: UUID,
        conversation_id: UUID,
        request_id: UUID,
        question: str,
        history: Sequence[ChatMessage],
    ) -> None:
        accumulated_text = ""
        steps: list[AgentStep] = []
        message_status: MessageStatus = "completed"
        terminal_published = False

        await self._broker.publish(
            assistant_message_id,
            "start",
            {
                "conversation_id": str(conversation_id),
                "assistant_message_id": str(assistant_message_id),
                "request_id": str(request_id),
            },
        )

        try:
            async for event in self._runtime.stream(question=question, history=history):
                if event.type is RuntimeEventType.STEP and event.step is not None:
                    steps.append(event.step)
                    await self._broker.publish(
                        assistant_message_id,
                        "step",
                        event.model_dump(mode="json"),
                    )
                elif event.type is RuntimeEventType.TEXT and event.text:
                    accumulated_text += event.text
                    await self._broker.publish(
                        assistant_message_id,
                        "text",
                        event.model_dump(mode="json"),
                    )
                elif event.type is RuntimeEventType.TEXT_RESET:
                    accumulated_text = ""
                    await self._broker.publish(
                        assistant_message_id,
                        "text_reset",
                        event.model_dump(mode="json"),
                    )
                elif event.type is RuntimeEventType.ERROR:
                    message_status = "error"
                    accumulated_text = event.message or "Agent execution failed."
                    await self._broker.publish(
                        assistant_message_id,
                        "error",
                        event.model_dump(mode="json"),
                    )
                    terminal_published = True
                    break
                elif event.type is RuntimeEventType.DONE:
                    status = str(event.data.get("status") or "completed")
                    if status != "completed":
                        message_status = "error"
                        accumulated_text = (
                            str(event.data.get("termination_reason"))
                            or f"Agent stopped with status: {status}"
                        )
                        await self._broker.publish(
                            assistant_message_id,
                            "error",
                            {
                                "assistant_message_id": str(assistant_message_id),
                                "message": accumulated_text,
                                "status": status,
                            },
                        )
                        terminal_published = True
                    break
        except asyncio.CancelledError:
            message_status = "aborted"
            await self._broker.publish(
                assistant_message_id,
                "aborted",
                {
                    "assistant_message_id": str(assistant_message_id),
                    "reason": "user_aborted",
                },
            )
            terminal_published = True
        except Exception as exc:
            message_status = "error"
            accumulated_text = f"{type(exc).__name__}: {exc}"
            await self._broker.publish(
                assistant_message_id,
                "error",
                {
                    "assistant_message_id": str(assistant_message_id),
                    "message": f"{type(exc).__name__}: {exc}",
                },
            )
            terminal_published = True
        finally:
            try:
                await asyncio.shield(
                    self._store.complete_assistant_message(
                        assistant_message_id,
                        content=accumulated_text,
                        status=message_status,
                        steps=steps,
                    )
                )
                persisted = True
            except Exception:
                persisted = False

            if not terminal_published:
                if message_status == "completed":
                    await self._broker.publish(
                        assistant_message_id,
                        "done",
                        {
                            "conversation_id": str(conversation_id),
                            "assistant_message_id": str(assistant_message_id),
                            "persisted": persisted,
                        },
                    )
                else:
                    await self._broker.publish(
                        assistant_message_id,
                        "error",
                        {
                            "assistant_message_id": str(assistant_message_id),
                            "message": "Agent task ended without a terminal event.",
                            "persisted": persisted,
                        },
                    )
