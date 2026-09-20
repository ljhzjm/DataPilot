import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import get_workspace_id
from app.db.models import Conversation, LLMUsageRecord, Message
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
                workspace_id = get_workspace_id()
                if usage.trace_id is not None:
                    row = (
                        await session.execute(
                            select(Message, Conversation.workspace_id)
                            .join(Conversation)
                            .where(Message.trace_id == usage.trace_id)
                        )
                    ).first()
                    if row is not None:
                        message, message_workspace_id = row
                        conversation_id = message.conversation_id
                        message_id = message.id
                        workspace_id = message_workspace_id
                if workspace_id is None:
                    logger.warning(
                        "Skipping workspace-less usage record request_id=%s",
                        usage.request_id,
                    )
                    return
                session.add(
                    LLMUsageRecord(
                        request_id=usage.request_id,
                        workspace_id=workspace_id,
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
