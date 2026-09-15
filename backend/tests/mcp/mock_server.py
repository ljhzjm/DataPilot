from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("DataPilot Mock MCP Server")


@mcp.tool(
    name="lookup_company",
    description="查询指定部门的示例公司信息。",
)
def lookup_company(
    department: Annotated[
        str,
        Field(min_length=1, description="部门名称。"),
    ],
) -> dict[str, str]:
    return {
        "department": department,
        "status": "active",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
