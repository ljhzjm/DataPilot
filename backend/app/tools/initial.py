import asyncio
from typing import Annotated, Any, Protocol
from uuid import UUID

from pydantic import Field

from app.core.context import require_workspace_id
from app.tools.chart import build_plot_chart_tool
from app.tools.duckdb_engine import (
    DuckDBAnalyticsEngine,
    QueryResult,
    TableInfo,
    TableSchema,
)
from app.tools.registry import RegisteredTool, ToolRegistry, tool
from app.tools.sql_guard import SQLPolicy


class AnalyticsEngine(Protocol):
    def list_tables(self) -> list[TableInfo]: ...

    def list_table_names(self) -> list[str]: ...

    def get_schema(self, table_name: str) -> TableSchema: ...

    def execute_select(self, sql: str, *, max_rows: int | None = None) -> QueryResult: ...


class WorkspaceDatasetAccess(Protocol):
    async def list_table_names(self, workspace_id: UUID) -> list[str]: ...


def build_initial_tools(
    engine: AnalyticsEngine,
    *,
    sql_policy: SQLPolicy | None = None,
    dataset_access: WorkspaceDatasetAccess | None = None,
) -> tuple[RegisteredTool, RegisteredTool, RegisteredTool, RegisteredTool]:
    policy = sql_policy or SQLPolicy()

    @tool(
        name="list_tables",
        description=(
            "做什么：列出当前分析库中的全部表。"
            "何时使用：用户询问有哪些数据、需要选择分析对象，"
            "或在编写 SQL 前确认表名时使用。"
            "参数：无。"
            "示例：{}。"
        ),
        parallel_safe=True,
    )
    async def list_tables_tool() -> dict[str, Any]:
        if dataset_access is None:
            tables = await asyncio.to_thread(engine.list_tables)
            table_payload = [table.model_dump(mode="json") for table in tables]
        else:
            names = await dataset_access.list_table_names(require_workspace_id())
            table_payload = [{"name": name, "table_type": "VIEW"} for name in names]
        return {
            "tables": table_payload,
            "count": len(table_payload),
        }

    @tool(
        name="get_schema",
        description=(
            "做什么：读取指定表的字段、类型和前几行样例数据。"
            "何时使用：生成 SQL 或编写 Python 分析代码前，"
            "需要了解列名、字段类型和示例值时使用。"
            "参数 table_name：当前分析库中已存在的表名。"
            '示例：{"table_name":"sales"}。'
        ),
        parallel_safe=True,
    )
    async def get_schema_tool(
        table_name: Annotated[
            str,
            Field(min_length=1, description="要读取结构的 DuckDB 表名。"),
        ],
    ) -> dict[str, Any]:
        if dataset_access is not None:
            allowed_tables = await dataset_access.list_table_names(require_workspace_id())
            if table_name not in allowed_tables:
                raise KeyError(f"Unknown table: {table_name}")
        schema = await asyncio.to_thread(engine.get_schema, table_name)
        return schema.model_dump(mode="json")

    @tool(
        name="run_sql",
        description=(
            "做什么：校验并执行只读 SELECT SQL，返回列名和有限行数的查询结果。"
            "何时使用：对已登记的数据表进行筛选、聚合、分组和趋势计算时使用。"
            "参数 sql：只能包含一条 SELECT；仅可使用当前分析库中的表，"
            "禁止写操作、外部文件函数和多语句。"
            '示例：{"sql":"SELECT region, SUM(amount) AS total FROM sales GROUP BY region"}。'
        ),
        parallel_safe=True,
    )
    async def run_sql_tool(
        sql: Annotated[
            str,
            Field(
                min_length=1,
                max_length=100_000,
                description="单条只读 SELECT SQL。",
            ),
        ],
    ) -> dict[str, Any]:
        allowed_tables = (
            await dataset_access.list_table_names(require_workspace_id())
            if dataset_access is not None
            else await asyncio.to_thread(engine.list_table_names)
        )
        safe_sql = policy.validate(sql, allowed_tables=allowed_tables)
        result = await asyncio.to_thread(engine.execute_select, safe_sql)
        return result.model_dump(mode="json")

    return list_tables_tool, get_schema_tool, run_sql_tool, build_plot_chart_tool()


def build_initial_registry(
    engine: AnalyticsEngine,
    *,
    sql_policy: SQLPolicy | None = None,
    dataset_access: WorkspaceDatasetAccess | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    for registered_tool in build_initial_tools(
        engine,
        sql_policy=sql_policy,
        dataset_access=dataset_access,
    ):
        registry.register(registered_tool)
    return registry


__all__ = [
    "AnalyticsEngine",
    "DuckDBAnalyticsEngine",
    "build_initial_registry",
    "build_initial_tools",
]
