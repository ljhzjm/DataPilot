from pathlib import Path
from uuid import UUID

import pytest

from app.core.context import reset_workspace_id, set_workspace_id
from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.initial import build_initial_tools
from app.tools.sql_guard import SQLValidationError


class FakeDatasetAccess:
    async def list_table_names(self, workspace_id: UUID) -> list[str]:
        del workspace_id
        return ["sales"]


@pytest.mark.asyncio
async def test_local_tools_only_expose_workspace_tables(tmp_path: Path) -> None:
    sales = tmp_path / "sales.csv"
    sales.write_text("region,amount\nEast,10\n", encoding="utf-8")
    secrets = tmp_path / "secrets.csv"
    secrets.write_text("value\nsecret\n", encoding="utf-8")
    engine = DuckDBAnalyticsEngine()
    engine.register_csv("sales", sales)
    engine.register_csv("secrets", secrets)
    list_tables, get_schema, run_sql, _ = build_initial_tools(
        engine,
        dataset_access=FakeDatasetAccess(),
    )
    token = set_workspace_id(UUID("00000000-0000-0000-0000-000000000001"))

    try:
        tables = await list_tables.invoke({})
        with pytest.raises(KeyError):
            await get_schema.invoke({"table_name": "secrets"})
        with pytest.raises(SQLValidationError):
            await run_sql.invoke({"sql": "SELECT * FROM secrets"})
    finally:
        reset_workspace_id(token)
        engine.close()

    assert tables == {
        "tables": [{"name": "sales", "table_type": "VIEW"}],
        "count": 1,
    }
