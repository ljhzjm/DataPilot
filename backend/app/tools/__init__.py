"""Tool definitions, registry, and built-in analytics tools."""

from app.tools.chart import ChartArtifact, ChartSpec, build_plot_chart_tool
from app.tools.definitions import FunctionDefinition, ToolDefinition
from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.initial import build_initial_registry, build_initial_tools
from app.tools.registry import RegisteredTool, ToolRegistry, tool
from app.tools.sql_guard import SQLPolicy, SQLValidationError

__all__ = [
    "DuckDBAnalyticsEngine",
    "ChartArtifact",
    "ChartSpec",
    "FunctionDefinition",
    "RegisteredTool",
    "SQLPolicy",
    "SQLValidationError",
    "ToolDefinition",
    "ToolRegistry",
    "build_initial_registry",
    "build_initial_tools",
    "build_plot_chart_tool",
    "tool",
]
