import asyncio
import json
import logging
import sys
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Literal, cast

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from app.tools.registry import (
    RegisteredTool,
    ToolRegistrationDiff,
    ToolRegistry,
)

logger = logging.getLogger(__name__)


class MCPToolCallError(RuntimeError):
    pass


class MCPConnectionError(MCPToolCallError):
    pass


@dataclass(frozen=True, slots=True)
class MCPClientStatus:
    connected: bool
    server_name: str | None
    protocol_version: str | None
    tool_count: int
    reconnect_count: int
    tool_refresh_count: int
    last_error: str | None
    last_connected_at: datetime | None
    last_ping_at: datetime | None


@dataclass(slots=True)
class _PendingRequest:
    kind: Literal["call", "refresh", "ping", "shutdown"]
    future: asyncio.Future[Any]
    name: str | None = None
    arguments: dict[str, Any] | None = None


class MCPClient:
    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        connect_attempts: int = 3,
        retry_base_delay_seconds: float = 0.5,
        retry_max_delay_seconds: float = 5,
        healthcheck_interval_seconds: float = 15,
        tool_refresh_interval_seconds: float = 300,
        call_retry_attempts: int = 1,
        connect_timeout_seconds: float = 10,
    ) -> None:
        self._command = command or sys.executable
        self._args = args or ["-m", "app.mcp.server"]
        self._cwd = Path(cwd).resolve() if cwd is not None else None
        self._env = dict(env) if env is not None else None
        self._connect_attempts = connect_attempts
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._retry_max_delay_seconds = retry_max_delay_seconds
        self._healthcheck_interval_seconds = healthcheck_interval_seconds
        self._tool_refresh_interval_seconds = tool_refresh_interval_seconds
        self._call_retry_attempts = call_retry_attempts
        self._connect_timeout_seconds = connect_timeout_seconds

        self._queue: asyncio.Queue[_PendingRequest] | None = None
        self._owner_task: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._startup_error: Exception | None = None
        self._closed = False

        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[types.Tool] = []
        self._registry: ToolRegistry | None = None
        self._server_name: str | None = None
        self._protocol_version: str | None = None
        self._last_error: str | None = None
        self._last_connected_at: datetime | None = None
        self._last_ping_at: datetime | None = None
        self._last_tool_refresh_at = 0.0
        self._reconnect_count = 0
        self._tool_refresh_count = 0
        self._ever_connected = False

    @property
    def tools(self) -> list[types.Tool]:
        return list(self._tools)

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def status(self) -> MCPClientStatus:
        return MCPClientStatus(
            connected=self.connected,
            server_name=self._server_name,
            protocol_version=self._protocol_version,
            tool_count=len(self._tools),
            reconnect_count=self._reconnect_count,
            tool_refresh_count=self._tool_refresh_count,
            last_error=self._last_error,
            last_connected_at=self._last_connected_at,
            last_ping_at=self._last_ping_at,
        )

    async def start(self) -> None:
        if self._closed:
            raise MCPConnectionError("MCP client is closed.")
        if self._owner_task is not None and not self._owner_task.done():
            return

        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._ready = loop.create_future()
        self._owner_task = asyncio.create_task(
            self._owner_loop(),
            name="mcp-client-owner",
        )
        await self._ready
        if self._startup_error is not None:
            raise MCPConnectionError(str(self._startup_error)) from self._startup_error

    async def close(self) -> None:
        if self._closed:
            return
        task = self._owner_task
        queue = self._queue
        if task is not None and not task.done() and queue is not None:
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            await queue.put(_PendingRequest(kind="shutdown", future=future))
            await future
            await task
        elif task is not None:
            await asyncio.gather(task, return_exceptions=True)
        self._closed = True

    def register_tools(self, registry: ToolRegistry) -> ToolRegistrationDiff:
        self._registry = registry
        return self._sync_registry()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self._submit(
            "call",
            name=name,
            arguments=arguments,
        )

    async def refresh_tools(self) -> ToolRegistrationDiff:
        return cast(ToolRegistrationDiff, await self._submit("refresh"))

    async def health(self) -> bool:
        return bool(await self._submit("ping"))

    async def _submit(
        self,
        kind: Literal["call", "refresh", "ping"],
        *,
        name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        queue = self._queue
        if self._closed or queue is None or self._owner_task is None:
            raise MCPConnectionError("MCP client is not started.")
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await queue.put(
            _PendingRequest(
                kind=kind,
                future=future,
                name=name,
                arguments=arguments,
            )
        )
        return await future

    async def _owner_loop(self) -> None:
        try:
            await self._connect_with_retries(self._connect_attempts)
        except Exception as exc:
            self._startup_error = exc
            self._set_error(exc)
        finally:
            if self._ready is not None and not self._ready.done():
                self._ready.set_result(None)

        while not self._closed:
            request: _PendingRequest | None = None
            queue = self._queue
            if queue is None:
                break
            try:
                request = await asyncio.wait_for(
                    queue.get(),
                    timeout=self._healthcheck_interval_seconds,
                )
            except TimeoutError:
                await self._maintenance()
                continue
            except asyncio.CancelledError:
                break

            if request.kind == "shutdown":
                try:
                    await self._disconnect()
                finally:
                    if not request.future.done():
                        request.future.set_result(None)
                break

            try:
                if request.kind == "call":
                    result = await self._handle_call(request)
                elif request.kind == "refresh":
                    result = await self._handle_refresh()
                else:
                    result = await self._handle_ping()
            except Exception as exc:
                if not request.future.done():
                    request.future.set_exception(exc)
            else:
                if not request.future.done():
                    request.future.set_result(result)

        await self._disconnect()

    async def _handle_call(self, request: _PendingRequest) -> Any:
        if request.name is None:
            raise MCPConnectionError("MCP tool name is missing.")
        arguments = request.arguments or {}
        if not self.connected:
            await self._connect_with_retries(self._connect_attempts)

        try:
            return await self._call_once(request.name, arguments)
        except MCPConnectionError as exc:
            self._set_error(exc)
            await self._disconnect()
        except MCPToolCallError:
            raise
        except Exception as exc:
            self._set_error(exc)
            await self._disconnect()

        last_error: Exception | None = None
        for _ in range(self._call_retry_attempts):
            try:
                await self._connect_with_retries(1)
                return await self._call_once(request.name, arguments)
            except MCPConnectionError as exc:
                last_error = exc
                self._set_error(exc)
                await self._disconnect()
            except MCPToolCallError:
                raise
            except Exception as exc:
                last_error = exc
                self._set_error(exc)
                await self._disconnect()
        raise MCPConnectionError(
            f"MCP tool '{request.name}' failed after reconnect."
        ) from last_error

    async def _handle_refresh(self) -> ToolRegistrationDiff:
        if not self.connected:
            await self._connect_with_retries(self._connect_attempts)
        return await self._refresh_tools()

    async def _handle_ping(self) -> bool:
        if not self.connected or self._session is None:
            return False
        try:
            async with asyncio.timeout(self._connect_timeout_seconds):
                await self._session.send_ping()
        except Exception as exc:
            self._set_error(exc)
            await self._disconnect()
            return False
        self._last_ping_at = datetime.now(UTC)
        return True

    async def _maintenance(self) -> None:
        if self._closed:
            return
        try:
            if not self.connected:
                await self._connect_with_retries(1)
            elif not await self._handle_ping():
                return

            now = monotonic()
            if (
                self.connected
                and self._tool_refresh_interval_seconds > 0
                and now - self._last_tool_refresh_at >= self._tool_refresh_interval_seconds
            ):
                await self._refresh_tools()
        except Exception as exc:
            self._set_error(exc)
            await self._disconnect()

    async def _connect_with_retries(self, attempts: int) -> None:
        last_error: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                await self._connect_once()
                return
            except Exception as exc:
                last_error = exc
                self._set_error(exc)
                if attempt + 1 < attempts:
                    delay = min(
                        self._retry_base_delay_seconds * (2**attempt),
                        self._retry_max_delay_seconds,
                    )
                    await asyncio.sleep(delay)
        raise MCPConnectionError(
            f"Unable to connect to MCP server after {max(1, attempts)} attempts."
        ) from last_error

    async def _connect_once(self) -> None:
        await self._disconnect()
        stack = AsyncExitStack()
        try:
            async with asyncio.timeout(self._connect_timeout_seconds):
                transport = await stack.enter_async_context(
                    stdio_client(
                        StdioServerParameters(
                            command=self._command,
                            args=self._args,
                            env=self._env,
                            cwd=self._cwd,
                        )
                    )
                )
                session = await stack.enter_async_context(
                    ClientSession(
                        read_stream=transport[0],
                        write_stream=transport[1],
                    )
                )
                initialize_result = await session.initialize()
                result = await session.list_tools()
            self._stack = stack
            self._session = session
            self._tools = list(result.tools)
            self._server_name = initialize_result.serverInfo.name
            self._protocol_version = str(initialize_result.protocolVersion)
            self._last_connected_at = datetime.now(UTC)
            self._last_ping_at = self._last_connected_at
            self._last_tool_refresh_at = monotonic()
            self._last_error = None
            if self._ever_connected:
                self._reconnect_count += 1
            self._ever_connected = True
            self._sync_registry()
        except Exception:
            try:
                await stack.aclose()
            except Exception as close_exc:
                logger.warning("Failed to close failed MCP connection: %s", close_exc)
            self._stack = None
            self._session = None
            raise

    async def _disconnect(self) -> None:
        stack = self._stack
        self._stack = None
        self._session = None
        if stack is not None:
            try:
                await stack.aclose()
            except Exception as exc:
                self._set_error(exc)
                logger.warning("Failed to close MCP connection cleanly: %s", exc)

    async def _refresh_tools(self) -> ToolRegistrationDiff:
        if self._session is None:
            raise MCPConnectionError("MCP client is not connected.")
        async with asyncio.timeout(self._connect_timeout_seconds):
            result = await self._session.list_tools()
        self._tools = list(result.tools)
        self._last_tool_refresh_at = monotonic()
        self._tool_refresh_count += 1
        return self._sync_registry()

    async def _call_once(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise MCPConnectionError("MCP client is not connected.")
        try:
            async with asyncio.timeout(self._connect_timeout_seconds):
                result = await self._session.call_tool(name, arguments)
        except Exception as exc:
            raise MCPConnectionError(f"MCP transport failed while calling '{name}': {exc}") from exc
        if result.isError:
            raise MCPToolCallError(_result_text(result) or f"MCP tool failed: {name}")
        if result.structuredContent is not None:
            return result.structuredContent
        return _parse_content(result)

    def _sync_registry(self) -> ToolRegistrationDiff:
        if self._registry is None:
            return ToolRegistrationDiff()
        try:
            return self._registry.replace_prefix(
                "mcp__",
                [self._to_registered_tool(tool) for tool in self._tools],
            )
        except Exception as exc:
            self._set_error(exc)
            logger.exception("Failed to synchronize MCP tools into the registry")
            return ToolRegistrationDiff()

    def _set_error(self, exc: Exception) -> None:
        self._last_error = f"{type(exc).__name__}: {exc}"

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


__all__ = [
    "MCPClient",
    "MCPClientStatus",
    "MCPConnectionError",
    "MCPToolCallError",
]
