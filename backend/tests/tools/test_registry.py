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
