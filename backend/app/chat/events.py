import asyncio
import json
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel
from redis.asyncio import Redis


class BrokerEvent(BaseModel):
    id: str
    event: str
    data: dict[str, Any]


class EventBroker(Protocol):
    async def publish(
        self,
        message_id: UUID,
        event: str,
        data: dict[str, Any],
    ) -> str: ...

    async def read(
        self,
        message_id: UUID,
        *,
        last_event_id: str,
        block_ms: int = 15_000,
        count: int = 100,
    ) -> list[BrokerEvent]: ...

    def stream_key(self, message_id: UUID) -> str: ...


class RedisEventBroker:
    def __init__(self, redis: Redis, *, max_events: int = 2000) -> None:
        self._redis = redis
        self._max_events = max_events

    def stream_key(self, message_id: UUID) -> str:
        return f"datapilot:chat:stream:{message_id}"

    async def publish(
        self,
        message_id: UUID,
        event: str,
        data: dict[str, Any],
    ) -> str:
        key = self.stream_key(message_id)
        event_id = await self._redis.xadd(
            key,
            {
                "event": event,
                "data": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            },
            maxlen=self._max_events,
            approximate=True,
        )
        await self._redis.expire(key, 24 * 60 * 60)
        return str(event_id)

    async def read(
        self,
        message_id: UUID,
        *,
        last_event_id: str,
        block_ms: int = 15_000,
        count: int = 100,
    ) -> list[BrokerEvent]:
        result = await self._redis.xread(
            {self.stream_key(message_id): last_event_id},
            count=count,
            block=block_ms if block_ms > 0 else None,
        )
        if not result:
            return []

        events: list[BrokerEvent] = []
        for _, entries in result:
            for event_id, fields in entries:
                events.append(
                    BrokerEvent(
                        id=str(event_id),
                        event=str(fields["event"]),
                        data=json.loads(str(fields["data"])),
                    )
                )
        return events


class InMemoryEventBroker:
    """Test and local fallback broker with Redis Stream-compatible event IDs."""

    def __init__(self) -> None:
        self._events: dict[str, deque[BrokerEvent]] = defaultdict(deque)
        self._counter = 0
        self._lock = asyncio.Lock()

    def stream_key(self, message_id: UUID) -> str:
        return f"datapilot:chat:stream:{message_id}"

    async def publish(
        self,
        message_id: UUID,
        event: str,
        data: dict[str, Any],
    ) -> str:
        async with self._lock:
            self._counter += 1
            event_id = f"{self._counter}-0"
            self._events[self.stream_key(message_id)].append(
                BrokerEvent(id=event_id, event=event, data=data)
            )
            return event_id

    async def read(
        self,
        message_id: UUID,
        *,
        last_event_id: str,
        block_ms: int = 15_000,
        count: int = 100,
    ) -> list[BrokerEvent]:
        del block_ms
        last_sequence = int(last_event_id.split("-", maxsplit=1)[0]) if last_event_id else 0
        events = [
            event
            for event in self._events[self.stream_key(message_id)]
            if int(event.id.split("-", maxsplit=1)[0]) > last_sequence
        ]
        return events[:count]

    async def watch(
        self,
        message_id: UUID,
        *,
        last_event_id: str,
    ) -> AsyncIterator[BrokerEvent]:
        cursor = last_event_id
        while True:
            events = await self.read(message_id, last_event_id=cursor)
            if not events:
                await asyncio.sleep(0.01)
                continue
            for event in events:
                cursor = event.id
                yield event
