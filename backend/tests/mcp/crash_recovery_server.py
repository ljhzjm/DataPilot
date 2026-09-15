import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

marker = Path(os.environ["MCP_TEST_MARKER"]).resolve()
mcp = FastMCP("DataPilot Crash Recovery MCP Server")


@mcp.tool(
    name="stop_and_recover",
    description=(
        "做什么：首次调用时让服务进程退出，后续调用返回恢复状态。"
        "何时使用：MCP 断线恢复集成测试。"
        "参数：无。"
        "示例：{}。"
    ),
)
def stop_and_recover() -> dict[str, bool]:
    if not marker.exists():
        marker.write_text("crashed", encoding="utf-8")
        os._exit(9)
    return {"recovered": True}


if marker.exists():

    @mcp.tool(
        name="recovered_tool",
        description=(
            "做什么：返回服务重启后的附加工具。"
            "何时使用：验证重连后工具列表刷新。"
            "参数：无。"
            "示例：{}。"
        ),
    )
    def recovered_tool() -> dict[str, str]:
        return {"status": "recovered"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
