import json
from collections.abc import Iterable
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.serialization import json_safe
from app.sandbox.models import ExecutionResult
from app.tools.sql_guard import SQLPolicy


class PostgresReadOnlyExecutor:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        allowed_tables: Iterable[str],
        statement_timeout_ms: int = 10_000,
        max_rows: int = 1000,
    ) -> None:
        if statement_timeout_ms < 1:
            raise ValueError("statement_timeout_ms must be positive.")
        if max_rows < 1:
            raise ValueError("max_rows must be positive.")

        self._engine = engine
        self._allowed_tables = frozenset(allowed_tables)
        self._statement_timeout_ms = statement_timeout_ms
        self._max_rows = max_rows
        self._sql_policy = SQLPolicy(
            dialect="postgres",
            allow_qualified_tables=True,
        )

    async def execute(self, sql: str) -> ExecutionResult:
        started = perf_counter()
        try:
            safe_sql = self._sql_policy.validate(sql, allowed_tables=self._allowed_tables)
            async with self._engine.connect() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                await connection.execute(
                    text(
                        f"SET LOCAL statement_timeout = {self._statement_timeout_ms}"  # noqa: S608
                    )
                )
                result = await connection.execute(text(safe_sql))
                columns = list(result.keys())
                raw_rows = result.fetchmany(self._max_rows + 1)
                await connection.rollback()

            truncated = len(raw_rows) > self._max_rows
            visible_rows = raw_rows[: self._max_rows]
            rows = [
                {column: json_safe(value) for column, value in zip(columns, row, strict=True)}
                for row in visible_rows
            ]
            payload = {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
            }
            return ExecutionResult(
                ok=True,
                stdout=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                truncated=truncated,
                duration_ms=(perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ExecutionResult(
                ok=False,
                stderr=f"{type(exc).__name__}: {exc}",
                duration_ms=(perf_counter() - started) * 1000,
            )
