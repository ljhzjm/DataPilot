import json

import httpx
import pytest

from app.sandbox.client import SandboxClient
from app.sandbox.models import SandboxDatasetMount


@pytest.mark.asyncio
async def test_sandbox_client_sends_token_and_parses_result() -> None:
    captured_token: str | None = None
    dataset_id = "11111111-1111-1111-1111-111111111111"

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_token
        captured_token = request.headers.get("X-Sandbox-Token")
        body = json.loads(request.content)
        assert body["code"] == "print(42)"
        assert body["data_mounts"] == [
            {
                "dataset_id": dataset_id,
                "target_name": "dataset_sales",
            }
        ]
        return httpx.Response(
            200,
            json={
                "ok": True,
                "stdout": "42\n",
                "stderr": "",
                "truncated": False,
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 2.5,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = SandboxClient(
            base_url="http://sandbox-runner:8100",
            token="test-token",
            client=http_client,
        )
        result = await client.execute(
            "print(42)",
            data_mounts=[
                SandboxDatasetMount.model_validate(
                    {
                        "dataset_id": dataset_id,
                        "target_name": "dataset_sales",
                    }
                )
            ],
        )

    assert captured_token == "test-token"
    assert result.ok is True
    assert result.stdout == "42\n"
