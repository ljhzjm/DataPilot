import asyncio
from collections.abc import Coroutine
from functools import partial
from typing import Any
from uuid import UUID


class ChatTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def start(
        self,
        message_id: UUID,
        coroutine: Coroutine[Any, Any, None],
    ) -> bool:
        existing = self._tasks.get(message_id)
        if existing is not None and not existing.done():
            coroutine.close()
            return False

        task = asyncio.create_task(coroutine, name=f"chat-task-{message_id}")
        self._tasks[message_id] = task
        task.add_done_callback(partial(self._discard, message_id))
        return True

    def abort(self, message_id: UUID) -> bool:
        task = self._tasks.get(message_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def is_running(self, message_id: UUID) -> bool:
        task = self._tasks.get(message_id)
        return task is not None and not task.done()

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _discard(self, message_id: UUID, task: asyncio.Task[None]) -> None:
        self._tasks.pop(message_id, None)
        try:
            task.exception()
        except asyncio.CancelledError:
            pass
