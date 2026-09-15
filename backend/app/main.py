import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.router import api_router
from app.chat.events import RedisEventBroker
from app.chat.runtime import build_chat_runtime
from app.chat.tasks import ChatTaskManager
from app.core.config import get_settings
from app.datasets.factory import build_dataset_service
from app.db.session import engine
from app.llm.factory import build_model_router
from app.mcp.client import MCPClient
from app.sandbox.client import SandboxClient
from app.sandbox.duckdb_executor import DuckDBReadOnlyExecutor
from app.sandbox.service import SandboxService
from app.tools.duckdb_engine import DuckDBAnalyticsEngine
from app.tools.initial import build_initial_registry

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.chat_event_broker = RedisEventBroker(app.state.redis)
    app.state.chat_task_manager = ChatTaskManager()
    app.state.analytics_engine = DuckDBAnalyticsEngine()
    app.state.tool_registry = build_initial_registry(app.state.analytics_engine)
    sandbox_client = SandboxClient()
    app.state.sandbox_client = sandbox_client
    app.state.sandbox_service = SandboxService(
        python_executor=sandbox_client,
        duckdb_executor=DuckDBReadOnlyExecutor(app.state.analytics_engine),
    )
    mcp_client: MCPClient | None = None
    if settings.mcp_enabled:
        mcp_client = MCPClient(
            command=settings.mcp_server_command,
            args=settings.mcp_server_args,
        )
        try:
            async with asyncio.timeout(settings.mcp_startup_timeout_seconds):
                await mcp_client.start()
            mcp_client.register_tools(app.state.tool_registry)
            app.state.mcp_error = None
        except Exception as exc:
            logger.exception("MCP startup failed")
            app.state.mcp_error = str(exc)
    app.state.mcp_client = mcp_client
    if settings.dataset_restore_on_startup:
        try:
            await build_dataset_service(app.state.analytics_engine).restore_engine()
        except Exception:
            logger.exception("Dataset restore failed")
    app.state.llm_router = build_model_router(settings)
    app.state.chat_runtime = build_chat_runtime(
        settings,
        model_router=app.state.llm_router,
        tool_registry=app.state.tool_registry,
    )
    try:
        yield
    finally:
        await app.state.chat_task_manager.shutdown()
        if mcp_client is not None:
            await mcp_client.close()
        if app.state.llm_router is not None:
            await app.state.llm_router.close()
        await sandbox_client.close()
        app.state.analytics_engine.close()
        await app.state.redis.aclose()
        await engine.dispose()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
