import asyncio
import json
from time import perf_counter

from app.core.serialization import json_safe
from app.sandbox.models import ExecutionResult
from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.sql_guard import SQLPolicy


class DuckDBReadOnlyExecutor:
    def __init__(
        self,
        engine: DuckDBAnalyticsEngine,
        *,
        sql_policy: SQLPolicy | None = None,
    ) -> None:
        self._engine = engine
        self._sql_policy = sql_policy or SQLPolicy()

    async def execute(self, sql: str) -> ExecutionResult:
        started = perf_counter()
        try:
            allowed_tables = await asyncio.to_thread(self._engine.list_table_names)
            safe_sql = self._sql_policy.validate(sql, allowed_tables=allowed_tables)
            result = await asyncio.to_thread(self._engine.execute_select, safe_sql)
            payload = {
                "columns": result.columns,
                "rows": [
                    {key: json_safe(value) for key, value in row.items()} for row in result.rows
                ],
                "row_count": result.row_count,
                "truncated": result.truncated,
            }
            return ExecutionResult(
                ok=True,
                stdout=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                truncated=result.truncated,
                duration_ms=(perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ExecutionResult(
                ok=False,
                stderr=f"{type(exc).__name__}: {exc}",
                duration_ms=(perf_counter() - started) * 1000,
            )
