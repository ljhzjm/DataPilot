from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import pytest

from app.agent.models import ChatMessage, LLMResponse, TokenUsage
from app.llm.base import EmbeddingResult, StreamEvent
from app.llm.cost import UsageRecord, UsageTrackingProvider
from app.llm.router import ModelRouter
from app.tools.definitions import ToolDefinition


class FakeProvider:
    def __init__(self) -> None:
        self.models: list[str | None] = []

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "default",
    ) -> LLMResponse:
        del messages, tools, trace_id, task
        self.models.append(model)
        return LLMResponse(
            content="ok",
            usage=TokenUsage(input_tokens=7, output_tokens=2),
        )

    async def chat_stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "default",
    ) -> AsyncIterator[StreamEvent]:
        del messages, tools, trace_id, task
        self.models.append(model)
        yield StreamEvent(
            type="usage",
            usage=TokenUsage(input_tokens=3, output_tokens=1),
        )

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "embedding",
    ) -> EmbeddingResult:
        del texts, trace_id, task
        self.models.append(model)
        return EmbeddingResult(
            model=model or "default",
            embeddings=[[0.1]],
            usage=TokenUsage(input_tokens=2),
        )

    async def close(self) -> None:
        return None


class RecordingUsageRecorder:
    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    async def record(self, usage: UsageRecord) -> None:
        self.records.append(usage)


@pytest.mark.asyncio
async def test_router_uses_task_specific_model_and_records_cost() -> None:
    provider = FakeProvider()
    recorder = RecordingUsageRecorder()
    tracked = UsageTrackingProvider(
        provider,
        provider_name="test-provider",
        recorder=recorder,
        input_price_per_million=1,
        output_price_per_million=2,
    )
    router = ModelRouter(
        provider=tracked,
        default_model="default-model",
        task_models={"sql": "sql-model", "intent": "fast-model"},
    )

    response = await router.chat(
        messages=[ChatMessage(role="user", content="统计销售额")],
        task="sql",
        trace_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    assert response.content == "ok"
    assert provider.models == ["sql-model"]
    assert router.model_for_task("intent") == "fast-model"
    assert router.model_for_task("unknown") == "default-model"
    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert record.model == "sql-model"
    assert record.task == "sql"
    assert record.trace_id == UUID("00000000-0000-0000-0000-000000000001")
    assert record.input_tokens == 7
    assert record.output_tokens == 2
    assert record.estimated_cost_usd == pytest.approx(0.000011)
    assert record.success is True


@pytest.mark.asyncio
async def test_usage_wrapper_records_stream_usage() -> None:
    recorder = RecordingUsageRecorder()
    tracked = UsageTrackingProvider(
        FakeProvider(),
        provider_name="test-provider",
        recorder=recorder,
    )

    events = [
        event
        async for event in tracked.chat_stream(
            messages=[ChatMessage(role="user", content="你好")],
            model="stream-model",
            task="default",
        )
    ]

    assert events[0].usage is not None
    assert recorder.records[0].model == "stream-model"
    assert recorder.records[0].input_tokens == 3
    assert recorder.records[0].output_tokens == 1
