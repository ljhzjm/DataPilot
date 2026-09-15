import asyncio
import os
from pathlib import Path

import pytest

from app.mcp.client import MCPClient, MCPConnectionError, MCPToolCallError
from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.initial import build_initial_registry
from app.tools.registry import ToolRegistry

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_mcp_client_discovers_and_calls_mock_server_tool() -> None:
    client = MCPClient(
        args=[str(BACKEND_ROOT / "tests" / "mcp" / "mock_server.py")],
        cwd=BACKEND_ROOT,
    )
    engine = DuckDBAnalyticsEngine()
    registry = build_initial_registry(engine)

    try:
        await client.start()
        client.register_tools(registry)

        definitions = registry.definitions()
        registered_tool = registry.get("mcp__lookup_company")
        assert registered_tool is not None
        result = await registered_tool.invoke({"department": "Sales"})
    finally:
        await client.close()
        engine.close()

    definition_names = [definition.function.name for definition in definitions]
    assert "get_schema" in definition_names
    assert "run_sql" in definition_names
    assert "plot_chart" in definition_names
    assert "mcp__lookup_company" in definition_names
    assert registered_tool.input_model is None
    assert registered_tool.input_schema is not None
    assert registered_tool.parallel_safe is False
    assert result == {
        "department": "Sales",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_mcp_client_validates_tool_arguments_before_call() -> None:
    client = MCPClient(
        args=[str(BACKEND_ROOT / "tests" / "mcp" / "mock_server.py")],
        cwd=BACKEND_ROOT,
    )
    registry = ToolRegistry()

    try:
        await client.start()
        client.register_tools(registry)
        registered_tool = registry.get("mcp__lookup_company")
        assert registered_tool is not None
        with pytest.raises(ValueError, match="Invalid arguments"):
            await registered_tool.invoke({})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_builtin_company_server_is_discoverable_and_read_only() -> None:
    client = MCPClient(cwd=BACKEND_ROOT)
    registry = ToolRegistry()

    try:
        await client.start()
        client.register_tools(registry)
        schema_tool = registry.get("mcp__get_company_schema")
        registered_tool = registry.get("mcp__query_company_data")
        assert schema_tool is not None
        assert registered_tool is not None
        schema = await schema_tool.invoke({})
        result = await registered_tool.invoke(
            {
                "sql": (
                    "SELECT department_id, SUM(salary) AS payroll "
                    "FROM employees GROUP BY department_id ORDER BY department_id"
                )
            }
        )
        with pytest.raises(MCPToolCallError, match="Only SELECT"):
            await registered_tool.invoke({"sql": "DELETE FROM employees"})
    finally:
        await client.close()

    assert result["rows"] == [
        {"department_id": 1, "payroll": "52000.00"},
        {"department_id": 2, "payroll": "44000.00"},
        {"department_id": 3, "payroll": "19000.00"},
    ]
    assert schema["count"] == 2
    assert [table["table_name"] for table in schema["tables"]] == [
        "departments",
        "employees",
    ]
    assert [column["name"] for column in schema["tables"][1]["columns"]] == [
        "id",
        "name",
        "department_id",
        "salary",
        "hire_date",
    ]


@pytest.mark.asyncio
async def test_mcp_client_reconnects_and_refreshes_tools(tmp_path: Path) -> None:
    marker = tmp_path / "crashed"
    client = MCPClient(
        args=[str(BACKEND_ROOT / "tests" / "mcp" / "crash_recovery_server.py")],
        cwd=BACKEND_ROOT,
        env={
            **os.environ,
            "MCP_TEST_MARKER": str(marker),
        },
        connect_attempts=2,
        retry_base_delay_seconds=0,
        connect_timeout_seconds=2,
    )
    registry = ToolRegistry()

    try:
        await client.start()
        client.register_tools(registry)
        assert registry.get("mcp__recovered_tool") is None

        tool = registry.get("mcp__stop_and_recover")
        assert tool is not None
        result = await tool.invoke({})

        assert result == {"recovered": True}
        assert client.connected is True
        assert client.status.reconnect_count == 1
        assert registry.get("mcp__recovered_tool") is not None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_retries_initial_startup(tmp_path: Path) -> None:
    counter = tmp_path / "start-count"
    client = MCPClient(
        args=[str(BACKEND_ROOT / "tests" / "mcp" / "flaky_startup_server.py")],
        cwd=BACKEND_ROOT,
        env={
            **os.environ,
            "MCP_TEST_START_COUNTER": str(counter),
            "MCP_TEST_REQUIRED_FAILURES": "1",
        },
        connect_attempts=3,
        retry_base_delay_seconds=0,
        connect_timeout_seconds=2,
    )
    registry = ToolRegistry()

    try:
        await client.start()
        client.register_tools(registry)

        assert client.connected is True
        assert counter.read_text(encoding="utf-8") == "2"
        assert registry.get("mcp__ready") is not None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_recovers_after_failed_startup(tmp_path: Path) -> None:
    counter = tmp_path / "background-start-count"
    client = MCPClient(
        args=[str(BACKEND_ROOT / "tests" / "mcp" / "flaky_startup_server.py")],
        cwd=BACKEND_ROOT,
        env={
            **os.environ,
            "MCP_TEST_START_COUNTER": str(counter),
            "MCP_TEST_REQUIRED_FAILURES": "1",
        },
        connect_attempts=1,
        retry_base_delay_seconds=0,
        connect_timeout_seconds=2,
        healthcheck_interval_seconds=0.05,
    )
    registry = ToolRegistry()
    client.register_tools(registry)

    try:
        with pytest.raises(MCPConnectionError):
            await client.start()

        for _ in range(40):
            if registry.get("mcp__ready") is not None:
                break
            await asyncio.sleep(0.05)

        assert client.connected is True
        assert registry.get("mcp__ready") is not None
    finally:
        await client.close()
