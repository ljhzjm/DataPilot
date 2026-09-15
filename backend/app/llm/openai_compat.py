import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

import httpx

from app.agent.models import ChatMessage, LLMResponse, TokenUsage, ToolCall
from app.llm.base import (
    EmbeddingResult,
    LLMResponseError,
    StreamEvent,
    ToolCallDelta,
)
from app.tools.definitions import ToolDefinition

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout_seconds: float = 60,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 0.5,
        include_usage_in_stream: bool = True,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty.")
        if not api_key.strip():
            raise ValueError("api_key must not be empty.")
        if not default_model.strip():
            raise ValueError("default_model must not be empty.")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative.")

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._max_retries = max_retries
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._include_usage_in_stream = include_usage_in_stream
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition] = (),
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "default",
    ) -> LLMResponse:
        del task, trace_id
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": _serialize_messages(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = [tool.model_dump(mode="json", exclude_none=True) for tool in tools]

        data = await self._request_json("/chat/completions", payload)
        try:
            choice = data["choices"][0]
            message = choice["message"]
            usage = data.get("usage") or {}
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Invalid chat completion response.") from exc

        return LLMResponse(
            content=message.get("content"),
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            ),
            finish_reason=choice.get("finish_reason"),
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
        del task, trace_id
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": _serialize_messages(messages),
            "stream": True,
        }
        if self._include_usage_in_stream:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = [tool.model_dump(mode="json", exclude_none=True) for tool in tools]

        emitted_data = False
        for attempt in range(self._max_retries + 1):
            try:
                async with self._client.stream(
                    "POST",
                    self._url("/chat/completions"),
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code in RETRYABLE_STATUS_CODES:
                        await response.aread()
                        if attempt < self._max_retries:
                            await self._sleep(self._backoff(attempt))
                            continue
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            return
                        emitted_data = True
                        event = _parse_stream_chunk(data)
                        if event is not None:
                            yield event
                    return
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if emitted_data or attempt >= self._max_retries:
                    raise
                await self._sleep(self._backoff(attempt))
                del exc

    async def embed(
        self,
        *,
        texts: Sequence[str],
        model: str | None = None,
        trace_id: UUID | None = None,
        task: str = "embedding",
    ) -> EmbeddingResult:
        del task, trace_id
        if not texts:
            return EmbeddingResult(
                model=model or self._default_model,
                embeddings=[],
            )
        data = await self._request_json(
            "/embeddings",
            {
                "model": model or self._default_model,
                "input": list(texts),
            },
        )
        try:
            embeddings = [[float(value) for value in item["embedding"]] for item in data["data"]]
            usage = data.get("usage") or {}
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMResponseError("Invalid embedding response.") from exc
        return EmbeddingResult(
            model=str(data.get("model") or model or self._default_model),
            embeddings=embeddings,
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=0,
            ),
        )

    async def _request_json(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    self._url(path),
                    headers=self._headers(),
                    json=payload,
                )
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt >= self._max_retries:
                    raise
                await self._sleep(self._backoff(attempt))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < self._max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
            if response.is_error:
                body = response.text[:2000]
                raise LLMResponseError(
                    f"Model provider returned HTTP {response.status_code}: {body}"
                )
            try:
                data = response.json()
            except ValueError as exc:
                raise LLMResponseError("Model provider returned invalid JSON.") from exc
            if not isinstance(data, dict):
                raise LLMResponseError("Model provider returned an invalid response body.")
            return data

        raise AssertionError("LLM retry loop exited unexpectedly.")

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _backoff(self, attempt: int) -> float:
        return float(self._retry_base_delay_seconds * (2**attempt))


def _serialize_messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for message in messages:
        payload: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.name:
            payload["name"] = message.name
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(
                            tool_call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
                for tool_call in message.tool_calls
            ]
        serialized.append(payload)
    return serialized


def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for raw_call in raw_calls:
        try:
            function = raw_call["function"]
            arguments = json.loads(function.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise LLMResponseError("Tool call arguments must be a JSON object.")
            calls.append(
                ToolCall(
                    id=str(raw_call["id"]),
                    name=str(function["name"]),
                    arguments=arguments,
                )
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseError("Invalid tool call response.") from exc
    return calls


def _parse_stream_chunk(data: str) -> StreamEvent | None:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None

    if usage := payload.get("usage"):
        return StreamEvent(
            type="usage",
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            ),
        )

    try:
        choice = payload["choices"][0]
        delta = choice.get("delta") or {}
    except (KeyError, IndexError, TypeError):
        return None

    if content := delta.get("content"):
        return StreamEvent(type="text_delta", content_delta=str(content))

    tool_calls = delta.get("tool_calls") or []
    if tool_calls:
        tool_call = tool_calls[0]
        function = tool_call.get("function") or {}
        return StreamEvent(
            type="tool_call_delta",
            tool_call_delta=ToolCallDelta(
                index=int(tool_call.get("index", 0)),
                id=tool_call.get("id"),
                name=function.get("name"),
                arguments_delta=function.get("arguments"),
            ),
        )

    if finish_reason := choice.get("finish_reason"):
        return StreamEvent(type="finish", finish_reason=str(finish_reason))
    return None
