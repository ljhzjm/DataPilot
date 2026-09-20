import time
from dataclasses import dataclass
from typing import Protocol

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings


class RateLimitStore(Protocol):
    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> bool: ...

    async def ttl(self, key: str) -> int: ...


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after: int


class RateLimiter:
    def __init__(self, store: RateLimitStore) -> None:
        self._store = store

    async def check(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        bucket = int(time.time() // window_seconds)
        redis_key = f"datapilot:rate:{key}:{bucket}"
        count = await self._store.incr(redis_key)
        if count == 1:
            await self._store.expire(redis_key, window_seconds)
        ttl = await self._store.ttl(redis_key)
        reset_after = max(1, ttl if ttl > 0 else window_seconds)
        return RateLimitResult(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            reset_after=reset_after,
        )


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _should_limit(scope):
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        path = str(scope.get("path") or "")
        state = scope.setdefault("state", {})
        auth = state.get("auth")
        identity = _identity(scope, auth)
        is_auth_endpoint = path in {"/api/auth/login", "/api/auth/register"}
        limit = (
            settings.auth_login_rate_limit_requests
            if is_auth_endpoint
            else settings.auth_rate_limit_requests
        )
        limiter = getattr(scope["app"].state, "rate_limiter", None)
        if not isinstance(limiter, RateLimiter):
            await self.app(scope, receive, send)
            return

        try:
            result = await limiter.check(
                key=identity,
                limit=limit,
                window_seconds=settings.auth_rate_limit_window_seconds,
            )
        except Exception:
            await self.app(scope, receive, send)
            return

        if not result.allowed:
            response = JSONResponse(
                {"detail": "Rate limit exceeded."},
                status_code=429,
                headers={
                    "Retry-After": str(result.reset_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_after),
                },
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-ratelimit-limit", str(result.limit).encode("ascii")),
                        (
                            b"x-ratelimit-remaining",
                            str(result.remaining).encode("ascii"),
                        ),
                        (
                            b"x-ratelimit-reset",
                            str(result.reset_after).encode("ascii"),
                        ),
                    ]
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _should_limit(scope: Scope) -> bool:
    path = str(scope.get("path") or "")
    method = str(scope.get("method") or "").upper()
    if method == "OPTIONS" or not path.startswith("/api/"):
        return False
    return not path.startswith(
        (
            "/api/health/",
            "/docs",
            "/redoc",
            "/openapi.json",
        )
    )


def _identity(scope: Scope, auth: object | None) -> str:
    workspace_id = getattr(auth, "workspace_id", None)
    if workspace_id is not None:
        return f"workspace:{workspace_id}"
    client = scope.get("client")
    host = client[0] if isinstance(client, tuple) and client else "unknown"
    return f"ip:{host}"
