from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.middleware import RequestAuth
from app.auth.schemas import (
    AuthSessionView,
    LoginRequest,
    RegisterRequest,
)
from app.auth.service import AuthContext, AuthError, AuthService
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(request: Request) -> AuthService:
    return cast(AuthService, request.app.state.auth_service)


@router.post(
    "/register",
    response_model=AuthSessionView,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSessionView:
    try:
        result = await service.register(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    _set_session_cookie(response, result.token)
    return result.session


@router.post("/login", response_model=AuthSessionView)
async def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSessionView:
    try:
        result = await service.login(
            username=payload.username,
            password=payload.password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _set_session_cookie(response, result.token)
    return result.session


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth = getattr(request.state, "auth", None)
    if auth is not None and auth.session_id is not None:
        await service.logout(auth.session_id)
    settings = get_settings()
    response.delete_cookie(
        settings.auth_session_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/me", response_model=AuthSessionView)
async def me(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSessionView:
    auth: RequestAuth | None = getattr(request.state, "auth", None)
    if auth is None or not auth.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    if auth.user_id is None or auth.session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    result = await service.current_session(
        context=_context_from_request(auth),
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer valid.",
        )
    return result


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _context_from_request(auth: RequestAuth) -> AuthContext:
    assert auth.user_id is not None
    assert auth.session_id is not None
    return AuthContext(
        user_id=auth.user_id,
        workspace_id=auth.workspace_id,
        session_id=auth.session_id,
        username=auth.username or "",
        display_name=auth.display_name or "",
    )
