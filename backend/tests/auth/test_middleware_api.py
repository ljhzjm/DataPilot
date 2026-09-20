from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth.middleware import AuthMiddleware
from app.auth.service import AuthContext
from app.core.config import Settings


class FakeAuthService:
    def __init__(self) -> None:
        self.user_id = uuid4()
        self.workspace_id = uuid4()
        self.session_id = uuid4()

    async def authenticate(self, token: str) -> AuthContext | None:
        if token != "valid-token":
            return None
        return AuthContext(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            session_id=self.session_id,
            username="alice",
            display_name="Alice",
        )


def test_auth_middleware_rejects_and_accepts_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeAuthService()
    settings = Settings(auth_enabled=True, auth_session_cookie_name="test_session")
    monkeypatch.setattr("app.auth.middleware.get_settings", lambda: settings)
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)
    test_app.state.auth_service = service

    @test_app.get("/api/protected")
    async def protected(request: Request) -> dict[str, str]:
        return {"workspace_id": str(request.state.auth.workspace_id)}

    with TestClient(test_app) as client:
        unauthorized = client.get("/api/protected")
        authorized = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer valid-token"},
        )
        cookie_authorized = client.get(
            "/api/protected",
            cookies={"test_session": "valid-token"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["workspace_id"] == str(service.workspace_id)
    assert cookie_authorized.status_code == 200


def test_auth_middleware_uses_default_workspace_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(auth_enabled=False)
    monkeypatch.setattr("app.auth.middleware.get_settings", lambda: settings)
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)

    @test_app.get("/api/protected")
    async def protected(request: Request) -> dict[str, str]:
        return {"workspace_id": str(request.state.auth.workspace_id)}

    with TestClient(test_app) as client:
        response = client.get("/api/protected")

    assert response.status_code == 200
    assert response.json()["workspace_id"] == "00000000-0000-0000-0000-000000000001"
