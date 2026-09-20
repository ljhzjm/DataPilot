from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import cast
from uuid import UUID

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.service import DEFAULT_WORKSPACE_ID, AuthContext
from app.core.config import get_settings

_PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/health/live",
    "/api/health/ready",
}


@dataclass(frozen=True, slots=True)
class RequestAuth:
    user_id: UUID | None
    workspace_id: UUID
    session_id: UUID | None
    username: str | None
    display_name: str | None
    authenticated: bool


class AuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "").upper()
        state = scope.setdefault("state", {})

        if not settings.auth_enabled:
            state["auth"] = RequestAuth(
                user_id=None,
                workspace_id=DEFAULT_WORKSPACE_ID,
                session_id=None,
                username=None,
                display_name=None,
                authenticated=False,
            )
            await self.app(scope, receive, send)
            return

        if method == "OPTIONS" or _is_public(path):
            await self.app(scope, receive, send)
            return

        token = _extract_token(scope, settings.auth_session_cookie_name)
        auth_service = getattr(scope["app"].state, "auth_service", None)
        context = None
        if token and auth_service is not None:
            context = await auth_service.authenticate(token)
        if context is None:
            response = JSONResponse(
                {"detail": "Authentication required."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        state["auth"] = _request_auth(context)
        await self.app(scope, receive, send)


def _request_auth(context: AuthContext) -> RequestAuth:
    return RequestAuth(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
        session_id=context.session_id,
        username=context.username,
        display_name=context.display_name,
        authenticated=True,
    )


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    return (
        path.startswith("/docs")
        or path.startswith("/redoc")
        or path == "/openapi.json"
        or not path.startswith("/api/")
    )


def _extract_token(scope: Scope, cookie_name: str) -> str | None:
    headers: dict[str, str] = {}
    for key, value in scope.get("headers", []):
        headers[bytes(key).decode("latin-1").lower()] = bytes(value).decode("latin-1")
    authorization = headers.get("authorization", "")
    if authorization.casefold().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token

    cookie_header = headers.get("cookie")
    if not cookie_header:
        return None
    cookies = SimpleCookie()
    try:
        cookies.load(cookie_header)
    except Exception:
        return None
    morsel = cookies.get(cookie_name)
    return cast(str, morsel.value) if morsel is not None else None
