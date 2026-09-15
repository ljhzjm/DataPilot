import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

counter_path = Path(os.environ["MCP_TEST_START_COUNTER"]).resolve()
required_failures = int(os.environ.get("MCP_TEST_REQUIRED_FAILURES", "1"))
start_count = int(counter_path.read_text(encoding="utf-8")) if counter_path.exists() else 0
counter_path.write_text(str(start_count + 1), encoding="utf-8")
if start_count < required_failures:
    sys.exit(17)

mcp = FastMCP("DataPilot Flaky Startup MCP Server")


@mcp.tool(
    name="ready",
    description=("做什么：返回 MCP Server 已启动。何时使用：验证启动重试。参数：无。示例：{}。"),
)
def ready() -> dict[str, str]:
    return {"status": "ready"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
