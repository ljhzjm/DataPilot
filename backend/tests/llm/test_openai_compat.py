import json
from typing import Any

import httpx
import pytest

from app.agent.models import ChatMessage
from app.llm.openai_compat import OpenAICompatibleProvider
from app.tools.definitions import ToolDefinition


@pytest.mark.asyncio
async def test_chat_parses_text_tool_calls_and_usage() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "run_sql",
                                        "arguments": '{"sql":"SELECT 1"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1",
            api_key="test-key",
            default_model="model-a",
            client=client,
        )
        response = await provider.chat(
            messages=[ChatMessage(role="user", content="查询")],
            tools=[
                ToolDefinition.model_validate(
                    {
                        "type": "function",
                        "function": {
                            "name": "run_sql",
                            "description": "执行 SQL",
                            "parameters": {
                                "type": "object",
                                "properties": {"sql": {"type": "string"}},
                                "required": ["sql"],
                            },
                        },
                    }
                )
            ],
        )

    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "model-a"
    assert response.tool_calls[0].name == "run_sql"
    assert response.tool_calls[0].arguments == {"sql": "SELECT 1"}
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 4
    assert response.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_chat_retries_429_before_success() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        del request
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "成功"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1",
            api_key="test-key",
            default_model="model-a",
            max_retries=2,
            retry_base_delay_seconds=0.25,
            client=client,
            sleep=fake_sleep,
        )
        response = await provider.chat(
            messages=[ChatMessage(role="user", content="你好")],
        )

    assert response.content == "成功"
    assert attempts == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_chat_stream_emits_text_tool_usage_and_finish_events() -> None:
    sse = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"分析"},"finish_reason":null}]}',
            (
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                '"id":"call-1","function":{"name":"run_sql",'
                '"arguments":"{\\"sql\\":\\"SELECT 1\\"}"}}]}}]}'
            ),
            ('data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3}}'),
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            text=sse,
            headers={"Content-Type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            base_url="https://model.example/v1",
            api_key="test-key",
            default_model="model-a",
            client=client,
        )
        events = [
            event
            async for event in provider.chat_stream(
                messages=[ChatMessage(role="user", content="查询")]
            )
        ]

    assert [event.type for event in events] == [
        "text_delta",
        "tool_call_delta",
        "usage",
        "finish",
    ]
    assert events[0].content_delta == "分析"
    assert events[1].tool_call_delta is not None
    assert events[1].tool_call_delta.name == "run_sql"
    assert events[2].usage is not None
    assert events[2].usage.total_tokens == 8
    assert events[3].finish_reason == "tool_calls"
