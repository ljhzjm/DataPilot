import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from app.tools.registry import RegisteredTool, ToolRegistry


class MCPToolCallError(RuntimeError):
    pass


class MCPClient:
    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        self._command = command or sys.executable
        self._args = args or ["-m", "app.mcp.server"]
        self._cwd = Path(cwd).resolve() if cwd is not None else None
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[types.Tool] = []

    @property
    def tools(self) -> list[types.Tool]:
        return list(self._tools)

    @property
    def connected(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        if self._session is not None:
            return

        stack = AsyncExitStack()
        try:
            transport = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=self._command,
                        args=self._args,
                        cwd=self._cwd,
                    )
                )
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream=transport[0], write_stream=transport[1])
            )
            await session.initialize()
            result = await session.list_tools()
            self._tools = list(result.tools)
            self._session = session
            self._stack = stack
        except Exception:
            await stack.aclose()
            raise

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None
        self._tools = []

    def register_tools(self, registry: ToolRegistry) -> None:
        for tool in self._tools:
            registry.register(self._to_registered_tool(tool))

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise MCPToolCallError("MCP client is not connected.")
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            raise MCPToolCallError(_result_text(result) or f"MCP tool failed: {name}")
        if result.structuredContent is not None:
            return result.structuredContent
        return _parse_content(result)

    def _to_registered_tool(self, tool: types.Tool) -> RegisteredTool:
        async def call(**arguments: Any) -> Any:
            return await self.call_tool(tool.name, arguments)

        return RegisteredTool(
            name=f"mcp__{tool.name}",
            description=f"[MCP] {tool.description or tool.title or tool.name}",
            input_model=None,
            input_schema=tool.inputSchema or {"type": "object", "properties": {}},
            handler=call,
            parallel_safe=False,
        )


def _parse_content(result: types.CallToolResult) -> Any:
    values: list[Any] = []
    for content in result.content:
        if isinstance(content, types.TextContent):
            values.append(_parse_text(content.text))
        elif isinstance(content, types.ImageContent):
            values.append(
                {
                    "type": "image",
                    "mime_type": content.mimeType,
                    "data": content.data,
                }
            )
        else:
            values.append(content.model_dump(mode="json"))

    if len(values) == 1:
        return values[0]
    return values


def _result_text(result: types.CallToolResult) -> str:
    return "\n".join(
        content.text for content in result.content if isinstance(content, types.TextContent)
    )


def _parse_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
