from pathlib import Path

import pytest

from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.initial import build_initial_tools
from app.tools.sql_guard import SQLValidationError


@pytest.mark.asyncio
async def test_initial_tools_list_schema_and_run_read_only_sql(tmp_path: Path) -> None:
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "region,amount\nEast,10\nWest,20\nEast,5\n",
        encoding="utf-8",
    )
    engine = DuckDBAnalyticsEngine()
    engine.register_csv("sales", csv_path)
    list_tables, get_schema, run_sql, _ = build_initial_tools(engine)

    try:
        tables = await list_tables.invoke({})
        schema = await get_schema.invoke({"table_name": "sales"})
        query = await run_sql.invoke(
            {
                "sql": (
                    "SELECT region, SUM(amount) AS total FROM sales GROUP BY region ORDER BY region"
                )
            }
        )
    finally:
        engine.close()

    assert tables["count"] == 1
    assert tables["tables"][0]["name"] == "sales"
    assert [column["name"] for column in schema["columns"]] == ["region", "amount"]
    assert len(schema["sample_rows"]) == 3
    assert query["rows"] == [
        {"region": "East", "total": 15},
        {"region": "West", "total": 20},
    ]


@pytest.mark.asyncio
async def test_initial_run_sql_rejects_write_operations(tmp_path: Path) -> None:
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("region,amount\nEast,10\n", encoding="utf-8")
    engine = DuckDBAnalyticsEngine()
    engine.register_csv("sales", csv_path)
    _, _, run_sql, _ = build_initial_tools(engine)

    try:
        with pytest.raises(SQLValidationError):
            await run_sql.invoke({"sql": "DELETE FROM sales"})
    finally:
        engine.close()
