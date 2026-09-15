from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from fastapi.testclient import TestClient

from app.sandbox.models import ExecutionResult, SandboxDatasetMount
from app.sandbox.runner_service import create_runner_app
from app.sandbox.service import PythonExecutor


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                str,
                Mapping[str, str | bytes] | None,
                list[SandboxDatasetMount],
            ]
        ] = []

    async def execute(
        self,
        code: str,
        *,
        input_files: Mapping[str, str | bytes] | None = None,
        data_mounts: list[SandboxDatasetMount] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        del timeout_seconds
        self.calls.append((code, input_files, data_mounts or []))
        return ExecutionResult(ok=True, stdout="42\n", exit_code=0)


def test_runner_requires_token_and_executes_fixed_request() -> None:
    executor = FakeExecutor()
    app = create_runner_app(
        executor=cast(PythonExecutor, executor),
        token="test-token",
    )

    with TestClient(app) as client:
        dataset_id = uuid4()
        unauthorized = client.post(
            "/v1/execute/python",
            json={"code": "print(42)"},
        )
        authorized = client.post(
            "/v1/execute/python",
            headers={"X-Sandbox-Token": "test-token"},
            json={
                "code": "print(42)",
                "input_files": {"input.txt": "21"},
                "data_mounts": [
                    {
                        "dataset_id": str(dataset_id),
                        "target_name": "dataset_sales",
                    }
                ],
            },
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["stdout"] == "42\n"
    assert executor.calls == [
        (
            "print(42)",
            {"input.txt": "21"},
            [
                SandboxDatasetMount(
                    dataset_id=dataset_id,
                    target_name="dataset_sales",
                )
            ],
        )
    ]


def test_runner_rejects_unknown_execution_fields() -> None:
    app = create_runner_app(
        executor=cast(PythonExecutor, FakeExecutor()),
        token="test-token",
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/execute/python",
            headers={"X-Sandbox-Token": "test-token"},
            json={
                "code": "print(42)",
                "image": "attacker/image",
            },
        )

    assert response.status_code == 422
