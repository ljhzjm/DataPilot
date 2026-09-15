from typing import Annotated

import pytest
from pydantic import Field, ValidationError

from app.tools.registry import ToolRegistry, tool


def test_tool_schema_is_generated_from_function_signature() -> None:
    @tool(
        name="lookup_region",
        description=(
            "做什么：查询区域。"
            "何时使用：用户提供区域名称时。"
            "参数 region：区域名称；limit：返回数量。"
            '示例：{"region":"East","limit":10}。'
        ),
    )
    async def lookup_region(
        region: Annotated[str, Field(description="区域名称。")],
        limit: Annotated[int, Field(ge=1, le=100, description="返回数量。")] = 10,
    ) -> str:
        return region

    parameters = lookup_region.definition.function.parameters

    assert parameters["additionalProperties"] is False
    assert parameters["required"] == ["region"]
    assert parameters["properties"]["region"]["description"] == "区域名称。"
    assert parameters["properties"]["limit"]["maximum"] == 100


@pytest.mark.asyncio
async def test_registry_validates_arguments_and_invokes_tool() -> None:
    registry = ToolRegistry()

    @tool(
        name="double",
        description=(
            "做什么：将数字乘以二。"
            "何时使用：测试工具注册表。"
            "参数 value：输入数字。"
            '示例：{"value":2}。'
        ),
    )
    async def double(value: int) -> int:
        return value * 2

    registry.register(double)

    assert await double.invoke({"value": 3}) == 6
    with pytest.raises(ValidationError):
        await double.invoke({"value": "not-an-int"})


def test_registry_replaces_namespaced_tools_without_touching_local_tools() -> None:
    registry = ToolRegistry()

    @tool(
        name="local_tool",
        description=("做什么：本地工具。何时使用：测试命名空间刷新。参数：无。示例：{}。"),
    )
    async def local_tool() -> str:
        return "local"

    @tool(
        name="mcp__lookup",
        description=("做什么：查询旧数据。何时使用：测试刷新。参数：无。示例：{}。"),
    )
    async def old_lookup() -> str:
        return "old"

    @tool(
        name="mcp__lookup",
        description=("做什么：查询新数据。何时使用：测试刷新。参数：无。示例：{}。"),
    )
    async def new_lookup() -> str:
        return "new"

    @tool(
        name="mcp__new_tool",
        description=("做什么：新增 MCP 工具。何时使用：测试刷新。参数：无。示例：{}。"),
    )
    async def new_tool() -> str:
        return "new-tool"

    @tool(
        name="mcp__stale",
        description=("做什么：已下线工具。何时使用：测试刷新。参数：无。示例：{}。"),
    )
    async def stale_tool() -> str:
        return "stale"

    registry.register(local_tool)
    registry.register(old_lookup)
    registry.register(stale_tool)

    diff = registry.replace_prefix("mcp__", [new_lookup, new_tool])

    assert diff.added == ("mcp__new_tool",)
    assert diff.updated == ("mcp__lookup",)
    assert diff.removed == ("mcp__stale",)
    assert registry.get("local_tool") is local_tool
    assert registry.get("mcp__lookup") is new_lookup
    assert registry.get("mcp__new_tool") is new_tool
    assert registry.get("mcp__stale") is None
