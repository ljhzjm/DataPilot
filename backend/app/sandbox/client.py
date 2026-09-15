from collections.abc import Mapping

import httpx

from app.core.config import get_settings
from app.sandbox.models import ExecutionResult, SandboxDatasetMount


class SandboxRunnerError(RuntimeError):
    pass


class SandboxClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.sandbox_runner_url).rstrip("/")
        self._token = token or (
            settings.sandbox_runner_token.get_secret_value()
            if settings.sandbox_runner_token is not None
            else ""
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds or settings.sandbox_runner_timeout_seconds)
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def execute(
        self,
        code: str,
        *,
        input_files: Mapping[str, str | bytes] | None = None,
        data_mounts: list[SandboxDatasetMount] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        files: dict[str, str] = {}
        for path, content in (input_files or {}).items():
            if isinstance(content, bytes):
                raise SandboxRunnerError(
                    "The remote sandbox runner only accepts UTF-8 input files."
                )
            files[path] = content

        try:
            response = await self._client.post(
                f"{self._base_url}/v1/execute/python",
                headers={"X-Sandbox-Token": self._token},
                json={
                    "code": code,
                    "input_files": files,
                    "data_mounts": [mount.model_dump(mode="json") for mount in (data_mounts or [])],
                    "timeout_seconds": timeout_seconds,
                },
            )
        except httpx.HTTPError as exc:
            return ExecutionResult(
                ok=False,
                stderr=f"Sandbox runner unavailable: {type(exc).__name__}",
            )

        if response.status_code != 200:
            detail = response.text[:1000]
            return ExecutionResult(
                ok=False,
                stderr=f"Sandbox runner rejected execution: {detail}",
            )
        try:
            return ExecutionResult.model_validate(response.json())
        except ValueError as exc:
            raise SandboxRunnerError("Sandbox runner returned an invalid response.") from exc

    async def health(self) -> bool:
        try:
            response = await self._client.get(
                f"{self._base_url}/health/live",
                timeout=2,
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200
