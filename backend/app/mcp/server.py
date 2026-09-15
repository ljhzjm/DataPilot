import logging
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.sql_guard import SQLPolicy

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "DataPilot Company Data",
    instructions=("只读公司示例数据分析服务。工具返回结构化查询结果，不会修改数据或访问外部网络。"),
)
_policy = SQLPolicy()


@mcp.tool(
    name="query_company_data",
    description=(
        "做什么：对 DataPilot 内置公司示例数据执行只读 SQL 查询。"
        "何时使用：已经通过 get_company_schema 确认字段后，"
        "需要查询 departments 或 employees 时使用。"
        "参数 sql：只允许单条 SELECT；只能使用 departments、employees。"
        "禁止查询 information_schema、系统表、外部文件或其他 schema。"
        "示例：SELECT department_id, SUM(salary) FROM employees GROUP BY department_id。"
    ),
)
def query_company_data(
    sql: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100_000,
            description="单条只读 DuckDB SELECT。",
        ),
    ],
) -> dict[str, Any]:
    try:
        safe_sql = _policy.validate(sql, allowed_tables=_engine.list_table_names())
    except ValueError as exc:
        raise ValueError(
            f"{exc} 公司 MCP 数据只允许 departments 和 employees；"
            "请先调用 get_company_schema 获取合法字段，"
            "不要查询 information_schema 或使用 schema 限定名称。"
        ) from exc
    result = _engine.execute_select(safe_sql)
    return result.model_dump(mode="json")


@mcp.tool(
    name="get_company_schema",
    description=(
        "做什么：读取公司示例数据的表结构和前 3 行样例。"
        "何时使用：查询 departments 或 employees 之前，"
        "需要确认表名、字段名和字段类型时使用。"
        "参数：无。"
        "示例：{}。"
    ),
)
def get_company_schema() -> dict[str, Any]:
    tables = [
        _engine.get_schema(table_name).model_dump(mode="json")
        for table_name in _engine.list_table_names()
    ]
    return {"tables": tables, "count": len(tables)}


def _build_engine() -> DuckDBAnalyticsEngine:
    engine = DuckDBAnalyticsEngine(max_query_rows=500)
    engine.register_rows(
        "departments",
        {"id": "INTEGER", "name": "VARCHAR", "location": "VARCHAR"},
        [
            (1, "Engineering", "Shanghai"),
            (2, "Sales", "Beijing"),
            (3, "Operations", "Shenzhen"),
        ],
    )
    engine.register_rows(
        "employees",
        {
            "id": "INTEGER",
            "name": "VARCHAR",
            "department_id": "INTEGER",
            "salary": "DECIMAL(12,2)",
            "hire_date": "DATE",
        },
        [
            (101, "Alice", 1, 28000, "2023-01-10"),
            (102, "Bob", 1, 24000, "2023-05-22"),
            (103, "Carol", 2, 21000, "2022-11-03"),
            (104, "David", 2, 23000, "2024-02-18"),
            (105, "Eve", 3, 19000, "2023-08-01"),
        ],
    )
    return engine


def main() -> None:
    mcp.run(transport="stdio")


_engine = _build_engine()


if __name__ == "__main__":
    main()
