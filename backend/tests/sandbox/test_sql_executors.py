import json
from pathlib import Path
from typing import Any, cast

import duckdb
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.sandbox.duckdb_executor import DuckDBReadOnlyExecutor
from app.sandbox.models import SandboxExecutionKind, SandboxRequest
from app.sandbox.postgres_executor import PostgresReadOnlyExecutor
from app.sandbox.service import SandboxService
from app.tools.duckdb_engine import DuckDBAnalyticsEngine


@pytest.mark.asyncio
async def test_sql_service_reads_csv_and_parquet(tmp_path: Path) -> None:
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("region,amount\nEast,10\nWest,20\n", encoding="utf-8")
    parquet_path = tmp_path / "targets.parquet"
    escaped_path = str(parquet_path).replace("'", "''")
    duckdb.sql(f"COPY (SELECT 'East' AS region, 100 AS target) TO '{escaped_path}'")

    engine = DuckDBAnalyticsEngine()
    engine.register_csv("sales", csv_path)
    engine.register_parquet("targets", parquet_path)
    service = SandboxService(
        duckdb_executor=DuckDBReadOnlyExecutor(engine),
    )

    try:
        result = await service.execute(
            SandboxRequest(
                kind=SandboxExecutionKind.DUCKDB,
                sql="SELECT SUM(amount) AS total FROM sales",
            )
        )
        parquet_result = await service.execute(
            SandboxRequest(
                kind=SandboxExecutionKind.DUCKDB,
                sql="SELECT target FROM targets",
            )
        )
    finally:
        engine.close()

    assert result.ok is True
    assert json.loads(result.stdout)["rows"] == [{"total": 30}]
    assert parquet_result.ok is True
    assert json.loads(parquet_result.stdout)["rows"] == [{"target": 100}]


@pytest.mark.asyncio
async def test_duckdb_executor_rejects_write_sql(tmp_path: Path) -> None:
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("region,amount\nEast,10\n", encoding="utf-8")
    engine = DuckDBAnalyticsEngine()
    engine.register_csv("sales", csv_path)
    executor = DuckDBReadOnlyExecutor(engine)

    try:
        delete_result = await executor.execute("DELETE FROM sales")
        insert_result = await executor.execute("INSERT INTO sales VALUES ('West', 20)")
    finally:
        engine.close()

    assert delete_result.ok is False
    assert "Only SELECT queries are allowed" in delete_result.stderr
    assert insert_result.ok is False
    assert "Only SELECT queries are allowed" in insert_result.stderr


class _FakeResult:
    def keys(self) -> list[str]:
        return ["value"]

    def fetchmany(self, size: int) -> list[tuple[int]]:
        return [(1,)]


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rolled_back = False

    async def execute(self, statement: Any) -> _FakeResult:
        self.statements.append(str(statement))
        return _FakeResult()

    async def rollback(self) -> None:
        self.rolled_back = True


class _FakeConnectionContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self._connection)


@pytest.mark.asyncio
async def test_postgres_executor_uses_read_only_transaction_and_rejects_writes() -> None:
    connection = _FakeConnection()
    executor = PostgresReadOnlyExecutor(
        cast(AsyncEngine, _FakeEngine(connection)),
        allowed_tables={"public.sales"},
    )

    select_result = await executor.execute("SELECT value FROM public.sales")
    statement_count = len(connection.statements)
    write_result = await executor.execute("DELETE FROM public.sales")

    assert select_result.ok is True
    assert json.loads(select_result.stdout)["rows"] == [{"value": 1}]
    assert connection.statements[0] == "SET TRANSACTION READ ONLY"
    assert connection.rolled_back is True
    assert write_result.ok is False
    assert "Only SELECT queries are allowed" in write_result.stderr
    assert len(connection.statements) == statement_count
