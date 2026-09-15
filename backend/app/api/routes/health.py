from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter()


class LiveResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, Literal["ok", "error"]]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request, response: Response) -> ReadyResponse:
    checks: dict[str, Literal["ok", "error"]] = {}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"

    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    if get_settings().mcp_enabled:
        mcp_client = getattr(request.app.state, "mcp_client", None)
        checks["mcp"] = "ok" if mcp_client is not None and mcp_client.connected else "error"

    sandbox_client = getattr(request.app.state, "sandbox_client", None)
    if sandbox_client is not None:
        checks["sandbox_runner"] = "ok" if await sandbox_client.health() else "error"

    if "error" in checks.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="degraded", checks=checks)

    return ReadyResponse(status="ok", checks=checks)
