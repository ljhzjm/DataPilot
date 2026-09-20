from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.artifacts.schemas import ArtifactView
from app.artifacts.service import ArtifactStore
from app.core.context import reset_workspace_id, set_workspace_id
from app.datasets.schemas import DatasetView
from app.sandbox.models import (
    ExecutionResult,
    SandboxArtifact,
    SandboxDatasetMount,
    SandboxRequest,
)
from app.tools.python import build_run_python_tool


class FakeDatasetResolver:
    def __init__(self, datasets: list[DatasetView]) -> None:
        self._datasets = datasets

    async def resolve_tables(
        self,
        workspace_id: UUID,
        table_names: list[str],
    ) -> list[DatasetView]:
        del workspace_id
        by_name = {dataset.table_name: dataset for dataset in self._datasets}
        if any(name not in by_name for name in table_names):
            raise ValueError("Dataset is unavailable.")
        return [by_name[name] for name in table_names]


class FakeSandboxService:
    def __init__(self) -> None:
        self.requests: list[SandboxRequest] = []

    async def execute(self, request: SandboxRequest) -> ExecutionResult:
        self.requests.append(request)
        return ExecutionResult(
            ok=True,
            stdout="wrote result\n",
            artifacts=[
                SandboxArtifact(
                    path="result.csv",
                    mime_type="text/csv",
                    size=4,
                    content_base64="dGVzdA==",
                )
            ],
        )


class FakeArtifactStore:
    async def persist(
        self,
        workspace_id: UUID,
        artifacts: list[SandboxArtifact],
    ) -> list[ArtifactView]:
        del workspace_id
        assert len(artifacts) == 1
        return [
            ArtifactView(
                id=uuid4(),
                filename="result.csv",
                mime_type="text/csv",
                size=4,
                url="/api/artifacts/example",
                created_at=datetime.now(UTC),
            )
        ]


def dataset_view(table_name: str) -> DatasetView:
    now = datetime.now(UTC)
    return DatasetView(
        id=uuid4(),
        name=table_name,
        original_filename=f"{table_name}.csv",
        table_name=table_name,
        file_type="csv",
        file_size=10,
        status="ready",
        row_count=1,
        columns=[],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def workspace_context() -> object:
    token = set_workspace_id(uuid4())
    yield
    reset_workspace_id(token)


@pytest.mark.asyncio
async def test_run_python_tool_mounts_only_resolved_datasets() -> None:
    dataset = dataset_view("dataset_sales")
    sandbox = FakeSandboxService()
    artifact_store = cast(ArtifactStore, FakeArtifactStore())
    run_python = build_run_python_tool(
        dataset_service=FakeDatasetResolver([dataset]),
        sandbox_service=sandbox,
        artifact_store=artifact_store,
    )

    result = await run_python.invoke(
        {
            "code": "print('ok')",
            "datasets": ["dataset_sales"],
        }
    )

    assert sandbox.requests[0].data_mounts == [
        SandboxDatasetMount(
            dataset_id=dataset.id,
            target_name=dataset.table_name,
        )
    ]
    assert result["ok"] is True
    assert result["artifacts"][0]["url"] == "/api/artifacts/example"
    assert "content_base64" not in result["artifacts"][0]


@pytest.mark.asyncio
async def test_run_python_tool_rejects_unavailable_dataset() -> None:
    run_python = build_run_python_tool(
        dataset_service=FakeDatasetResolver([]),
        sandbox_service=FakeSandboxService(),
        artifact_store=cast(ArtifactStore, FakeArtifactStore()),
    )

    with pytest.raises(ValueError, match="unavailable"):
        await run_python.invoke(
            {
                "code": "print('ok')",
                "datasets": ["dataset_missing"],
            }
        )


def test_run_python_tool_schema_limits_dataset_count() -> None:
    run_python = build_run_python_tool(
        dataset_service=FakeDatasetResolver([]),
        sandbox_service=FakeSandboxService(),
        artifact_store=cast(ArtifactStore, FakeArtifactStore()),
    )

    schema = run_python.definition.function.parameters

    assert schema["properties"]["datasets"]["maxItems"] == 5
    assert schema["required"] == ["code", "datasets"]


@pytest.mark.asyncio
async def test_run_python_tool_stops_before_executing_over_300_lines() -> None:
    sandbox = FakeSandboxService()
    run_python = build_run_python_tool(
        dataset_service=FakeDatasetResolver([dataset_view("dataset_sales")]),
        sandbox_service=sandbox,
        artifact_store=cast(ArtifactStore, FakeArtifactStore()),
    )

    with pytest.raises(ValueError, match="manual review"):
        await run_python.invoke(
            {
                "code": "\n".join("pass" for _ in range(301)),
                "datasets": ["dataset_sales"],
            }
        )

    assert sandbox.requests == []
