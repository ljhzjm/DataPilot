import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import LLMUsageRecord, Message
from app.llm.cost import UsageRecord

logger = logging.getLogger(__name__)


class DatabaseUsageRecorder:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def record(self, usage: UsageRecord) -> None:
        try:
            async with self._session_factory() as session:
                conversation_id = None
                message_id = None
                if usage.trace_id is not None:
                    message = await session.scalar(
                        select(Message).where(Message.trace_id == usage.trace_id)
                    )
                    if message is not None:
                        conversation_id = message.conversation_id
                        message_id = message.id
                session.add(
                    LLMUsageRecord(
                        request_id=usage.request_id,
                        trace_id=usage.trace_id,
                        conversation_id=conversation_id,
                        message_id=message_id,
                        task=usage.task,
                        provider=usage.provider,
                        model=usage.model,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        estimated_cost_usd=Decimal(str(usage.estimated_cost_usd)),
                        latency_ms=usage.latency_ms,
                        success=usage.success,
                        error_type=usage.error_type,
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "Failed to persist usage record request_id=%s",
                usage.request_id,
            )
