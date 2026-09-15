import logging
from collections.abc import AsyncIterator, Sequence
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agent.models import ChatMessage, LLMResponse, TokenUsage
from app.llm.base import EmbeddingResult, LLMProvider, StreamEvent
from app.tools.definitions import ToolDefinition

logger = logging.getLogger(__name__)


class UsageRecord(BaseModel):
    request_id: str
    trace_id: str | None = None
    task: str
    provider: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    success: bool
    error_type: str | None = None


class UsageRecorder(Protocol):
    async def record(self, usage: UsageRecord) -> None: ...


class LoggingUsageRecorder:
    async def record(self, usage: UsageRecord) -> None:
        logger.info(
            "llm_usage request_id=%s trace_id=%s task=%s provider=%s model=%s "
            "input_tokens=%s output_tokens=%s latency_ms=%.2f success=%s error_type=%s",
            usage.request_id,
            usage.trace_id,
            usage.task,
            usage.provider,
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
            usage.latency_ms,
            usage.success,
            usage.error_type,
        )


class UsageTrackingProvider:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        provider_name: str,
        recorder: UsageRecorder | None = None,
    ) -> None:
        self._provider = provider
        self._provider_name = provider_name
        self._recorder = recorder or LoggingUsageRecorder()

    async def close(self) -> None:
        await self._provider.close()

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: str | None = None,
        task: str = "default",
    ) -> LLMResponse:
        started = perf_counter()
        try:
            response = await self._provider.chat(
                messages=messages,
                tools=tools,
                model=model,
                trace_id=trace_id,
            )
        except Exception as exc:
            await self._record(
                task=task,
                model=model,
                trace_id=trace_id,
                usage=TokenUsage(),
                started=started,
                success=False,
                error_type=type(exc).__name__,
            )
            raise
        await self._record(
            task=task,
            model=model,
            trace_id=trace_id,
            usage=response.usage,
            started=started,
            success=True,
        )
        return response

    async def chat_stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: str | None = None,
        task: str = "default",
    ) -> AsyncIterator[StreamEvent]:
        started = perf_counter()
        usage = TokenUsage()
        success = True
        error_type: str | None = None
        try:
            async for event in self._provider.chat_stream(
                messages=messages,
                tools=tools,
                model=model,
                trace_id=trace_id,
            ):
                if event.usage is not None:
                    usage = event.usage
                yield event
        except BaseException as exc:
            success = False
            error_type = type(exc).__name__
            raise
        finally:
            await self._record(
                task=task,
                model=model,
                trace_id=trace_id,
                usage=usage,
                started=started,
                success=success,
                error_type=error_type,
            )

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str | None = None,
        trace_id: str | None = None,
        task: str = "embedding",
    ) -> EmbeddingResult:
        started = perf_counter()
        try:
            result = await self._provider.embed(
                texts=texts,
                model=model,
                trace_id=trace_id,
            )
        except Exception as exc:
            await self._record(
                task=task,
                model=model,
                trace_id=trace_id,
                usage=TokenUsage(),
                started=started,
                success=False,
                error_type=type(exc).__name__,
            )
            raise
        await self._record(
            task=task,
            model=model,
            trace_id=trace_id,
            usage=result.usage,
            started=started,
            success=True,
        )
        return result

    async def _record(
        self,
        *,
        task: str,
        model: str | None,
        trace_id: str | None,
        usage: TokenUsage,
        started: float,
        success: bool,
        error_type: str | None = None,
    ) -> None:
        await self._recorder.record(
            UsageRecord(
                request_id=uuid4().hex,
                trace_id=trace_id,
                task=task,
                provider=self._provider_name,
                model=model or "default",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=(perf_counter() - started) * 1000,
                success=success,
                error_type=error_type,
            )
        )
