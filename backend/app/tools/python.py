from typing import Annotated, Any, Protocol

from pydantic import Field

from app.artifacts.service import ArtifactStore
from app.datasets.schemas import DatasetView
from app.sandbox.models import (
    ExecutionResult,
    SandboxDatasetMount,
    SandboxExecutionKind,
    SandboxRequest,
)
from app.tools.registry import RegisteredTool, tool

_MAX_GENERATED_CODE_LINES = 300
_MAX_DATASET_MOUNTS = 5


class DatasetResolver(Protocol):
    async def resolve_tables(self, table_names: list[str]) -> list[DatasetView]: ...


class SandboxExecutor(Protocol):
    async def execute(self, request: SandboxRequest) -> ExecutionResult: ...


def build_run_python_tool(
    *,
    dataset_service: DatasetResolver,
    sandbox_service: SandboxExecutor,
    artifact_store: ArtifactStore,
) -> RegisteredTool:
    @tool(
        name="run_python",
        description=(
            "做什么：在断网 Docker 沙箱中执行 Python 分析代码，并可读取已登记的 Parquet 数据集。"
            "何时使用：问题需要 SQL 难以完成的统计建模、数据清洗、透视或文件导出时使用；"
            "简单筛选和聚合优先使用 run_sql。"
            "参数 code：Python 源码。数据集以只读方式挂载到 "
            "/data/<table_name>/data.parquet。"
            "参数 datasets：要通过挂载读取的数据表名列表，最多 5 个。"
            "生成的文件必须写入 /workspace/outputs，支持 .csv、.json、.png。"
            "示例："
            '{"code":"import pandas as pd; '
            "df=pd.read_parquet('/data/dataset_abc/data.parquet'); "
            "df.to_csv('/workspace/outputs/result.csv', index=False)\","
            '"datasets":["dataset_abc"]}。'
        ),
        parallel_safe=False,
    )
    async def run_python(
        code: Annotated[
            str,
            Field(
                min_length=1,
                max_length=80_000,
                description="要把完整源码写入沙箱 /workspace/main.py 的 Python 代码。",
            ),
        ],
        datasets: Annotated[
            list[str],
            Field(
                min_length=1,
                max_length=_MAX_DATASET_MOUNTS,
                description="要只读挂载的数据表名；每个表可用 /data/<table_name>/data.parquet。",
            ),
        ],
    ) -> dict[str, Any]:
        if len(code.splitlines()) > _MAX_GENERATED_CODE_LINES:
            raise ValueError(
                f"Generated Python exceeds {_MAX_GENERATED_CODE_LINES} lines "
                "and requires manual review."
            )
        if len(set(datasets)) != len(datasets):
            raise ValueError("Dataset names must be unique.")

        resolved = await dataset_service.resolve_tables(datasets)
        mounts = [
            SandboxDatasetMount(
                dataset_id=dataset.id,
                target_name=dataset.table_name,
            )
            for dataset in resolved
        ]
        result = await sandbox_service.execute(
            SandboxRequest(
                kind=SandboxExecutionKind.PYTHON,
                code=code,
                data_mounts=mounts,
            )
        )
        artifacts = await artifact_store.persist(result.artifacts)
        return {
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "truncated": result.truncated,
            "timed_out": result.timed_out,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        }

    return run_python


__all__ = ["build_run_python_tool"]
