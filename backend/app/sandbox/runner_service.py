import hmac
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.sandbox.models import ExecutionResult
from app.sandbox.python_executor import DockerPythonExecutor
from app.sandbox.service import PythonExecutor


class SandboxExecuteRequest(BaseModel):
    code: str = Field(min_length=1)
    input_files: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0, le=60)

    model_config = ConfigDict(extra="forbid")


def create_runner_app(
    *,
    executor: PythonExecutor | None = None,
    token: str | None = None,
) -> FastAPI:
    app = FastAPI(title="DataPilot Sandbox Runner", docs_url=None, redoc_url=None)
    execution_backend = executor or DockerPythonExecutor()

    def require_token(
        x_sandbox_token: Annotated[str | None, Header()] = None,
    ) -> None:
        settings = get_settings()
        expected = token
        if expected is None:
            expected = (
                settings.sandbox_runner_token.get_secret_value()
                if settings.sandbox_runner_token is not None
                else ""
            )
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sandbox runner token is not configured.",
            )
        if not x_sandbox_token or not hmac.compare_digest(x_sandbox_token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid sandbox runner token.",
            )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/execute/python",
        response_model=ExecutionResult,
        dependencies=[Depends(require_token)],
    )
    async def execute_python(payload: SandboxExecuteRequest) -> ExecutionResult:
        return await execution_backend.execute(
            payload.code,
            input_files=payload.input_files,
            timeout_seconds=payload.timeout_seconds,
        )

    return app


app = create_runner_app()
