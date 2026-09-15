from collections.abc import AsyncIterator, Sequence

from app.agent.models import ChatMessage, LLMResponse
from app.llm.base import EmbeddingResult, LLMProvider, StreamEvent
from app.tools.definitions import ToolDefinition


class ModelRouter:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        default_model: str,
        task_models: dict[str, str] | None = None,
    ) -> None:
        self._provider = provider
        self._default_model = default_model
        self._task_models = dict(task_models or {})

    def model_for_task(self, task: str) -> str:
        return self._task_models.get(task, self._default_model)

    async def close(self) -> None:
        await self._provider.close()

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        task: str = "default",
        trace_id: str | None = None,
    ) -> LLMResponse:
        return await self._provider.chat(
            messages=messages,
            tools=tools,
            model=self.model_for_task(task),
            trace_id=trace_id,
            task=task,
        )

    def chat_stream(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        task: str = "default",
        trace_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        return self._provider.chat_stream(
            messages=messages,
            tools=tools,
            model=self.model_for_task(task),
            trace_id=trace_id,
            task=task,
        )

    async def embed(
        self,
        *,
        texts: Sequence[str],
        task: str = "embedding",
        trace_id: str | None = None,
    ) -> EmbeddingResult:
        return await self._provider.embed(
            texts=texts,
            model=self.model_for_task(task),
            trace_id=trace_id,
            task=task,
        )
