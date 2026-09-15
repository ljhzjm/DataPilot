from collections.abc import Mapping
from typing import Protocol

from app.sandbox.duckdb_executor import DuckDBReadOnlyExecutor
from app.sandbox.models import ExecutionResult, SandboxExecutionKind, SandboxRequest
from app.sandbox.postgres_executor import PostgresReadOnlyExecutor


class PythonExecutor(Protocol):
    async def execute(
        self,
        code: str,
        *,
        input_files: Mapping[str, str | bytes] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult: ...


class SandboxService:
    def __init__(
        self,
        *,
        python_executor: PythonExecutor | None = None,
        duckdb_executor: DuckDBReadOnlyExecutor | None = None,
        postgres_executor: PostgresReadOnlyExecutor | None = None,
    ) -> None:
        self._python_executor = python_executor
        self._duckdb_executor = duckdb_executor
        self._postgres_executor = postgres_executor

    async def execute(self, request: SandboxRequest) -> ExecutionResult:
        if request.kind is SandboxExecutionKind.PYTHON:
            if self._python_executor is None:
                return ExecutionResult(ok=False, stderr="Python sandbox is not configured.")
            return await self._python_executor.execute(
                request.code or "",
                input_files=request.input_files,
                timeout_seconds=request.timeout_seconds,
            )

        if request.kind is SandboxExecutionKind.DUCKDB:
            if self._duckdb_executor is None:
                return ExecutionResult(ok=False, stderr="DuckDB executor is not configured.")
            return await self._duckdb_executor.execute(request.sql or "")

        if self._postgres_executor is None:
            return ExecutionResult(ok=False, stderr="PostgreSQL executor is not configured.")
        return await self._postgres_executor.execute(request.sql or "")
