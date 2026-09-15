import asyncio
import base64
import json
from collections.abc import Mapping
from time import perf_counter, perf_counter_ns

import requests
from docker import DockerClient
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.types import Ulimit

from app.core.config import get_settings
from app.sandbox.models import ExecutionResult


class SandboxUnavailableError(RuntimeError):
    pass


class DockerPythonExecutor:
    def __init__(
        self,
        *,
        client: DockerClient | None = None,
        image: str | None = None,
        timeout_seconds: float | None = None,
        memory_limit: str | None = None,
        pids_limit: int | None = None,
        cpu_limit: float | None = None,
        output_limit_bytes: int | None = None,
        max_code_lines: int | None = None,
        max_code_chars: int | None = None,
        max_input_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self._owns_client = client is None
        self._client = client or DockerClient.from_env()
        self._image = image or settings.sandbox_image
        self._timeout_seconds = timeout_seconds or settings.sandbox_timeout_seconds
        self._memory_limit = memory_limit or settings.sandbox_memory_limit
        self._pids_limit = pids_limit or settings.sandbox_pids_limit
        self._cpu_limit = cpu_limit or settings.sandbox_cpu_limit
        self._output_limit_bytes = output_limit_bytes or settings.sandbox_output_limit_bytes
        self._max_code_lines = max_code_lines or settings.sandbox_max_code_lines
        self._max_code_chars = max_code_chars or settings.sandbox_max_code_chars
        self._max_input_bytes = max_input_bytes or settings.sandbox_max_input_bytes

    async def close(self) -> None:
        if self._owns_client:
            self._client.close()

    async def execute(
        self,
        code: str,
        *,
        input_files: Mapping[str, str | bytes] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        validation_error = self._validate_payload(code, input_files or {})
        if validation_error:
            return ExecutionResult(ok=False, stderr=validation_error)

        effective_timeout = min(
            timeout_seconds or self._timeout_seconds,
            self._timeout_seconds,
        )
        return await asyncio.to_thread(
            self._execute_sync,
            code,
            input_files or {},
            effective_timeout,
        )

    def _execute_sync(
        self,
        code: str,
        input_files: Mapping[str, str | bytes],
        effective_timeout: float,
    ) -> ExecutionResult:
        started = perf_counter()
        container: Container | None = None

        try:
            self._client.images.get(self._image)
        except ImageNotFound as exc:
            raise SandboxUnavailableError(
                f"Sandbox image is not available: {self._image}. "
                "Run `docker compose --profile sandbox build sandbox`."
            ) from exc
        except DockerException as exc:
            raise SandboxUnavailableError("Docker daemon is not available.") from exc

        try:
            environment = {
                "SANDBOX_CODE_B64": base64.b64encode(code.encode("utf-8")).decode("ascii"),
                "SANDBOX_FILES_B64": _encode_input_files(input_files),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "MPLBACKEND": "Agg",
                "MPLCONFIGDIR": "/tmp/matplotlib",  # noqa: S108
                "HOME": "/tmp",  # noqa: S108
            }
            container = self._client.containers.create(
                image=self._image,
                command=["python", "/opt/sandbox/runner.py"],
                name=f"datapilot-sandbox-{perf_counter_ns()}",
                detach=True,
                network_disabled=True,
                mem_limit=self._memory_limit,
                pids_limit=self._pids_limit,
                nano_cpus=int(self._cpu_limit * 1_000_000_000),
                read_only=True,
                tmpfs={
                    "/workspace": "size=128m,uid=10001,gid=10001,mode=0700,noexec,nosuid,nodev",
                    "/tmp": (  # noqa: S108
                        "size=64m,uid=10001,gid=10001,mode=0700,noexec,nosuid,nodev"
                    ),
                },
                working_dir="/workspace",
                user="10001:10001",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                init=True,
                environment=environment,
                labels={"datapilot.sandbox": "true"},
                ulimits=[Ulimit(Name="nofile", Soft=256, Hard=256)],
            )
            container.start()

            timed_out = False
            try:
                wait_result = container.wait(timeout=effective_timeout)
                exit_code = int(wait_result["StatusCode"])
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ):
                timed_out = True
                exit_code = None
                self._kill_quietly(container)
            except DockerException:
                timed_out = True
                exit_code = None
                self._kill_quietly(container)

            stdout, stdout_truncated = self._read_logs(container, stderr=False)
            stderr, stderr_truncated = self._read_logs(container, stderr=True)
            if timed_out:
                timeout_message = f"Execution timed out after {effective_timeout:g} seconds."
                stderr = f"{stderr}\n{timeout_message}".strip()

            return ExecutionResult(
                ok=not timed_out and exit_code == 0,
                stdout=stdout,
                stderr=stderr,
                truncated=stdout_truncated or stderr_truncated,
                exit_code=exit_code,
                timed_out=timed_out,
                duration_ms=(perf_counter() - started) * 1000,
            )
        except DockerException as exc:
            return ExecutionResult(
                ok=False,
                stderr=f"Docker sandbox execution failed: {exc}",
                duration_ms=(perf_counter() - started) * 1000,
            )
        finally:
            if container is not None:
                self._remove_quietly(container)

    def _validate_payload(
        self,
        code: str,
        input_files: Mapping[str, str | bytes],
    ) -> str | None:
        if not code.strip():
            return "Python code must not be empty."
        if len(code) > self._max_code_chars:
            return f"Python code exceeds {self._max_code_chars} characters."
        if len(code.splitlines()) > self._max_code_lines:
            return f"Python code exceeds {self._max_code_lines} lines and requires manual review."

        total_input_bytes = 0
        for relative_path, content in input_files.items():
            self._validate_relative_path(relative_path)
            total_input_bytes += (
                len(content) if isinstance(content, bytes) else len(content.encode("utf-8"))
            )
        if total_input_bytes > self._max_input_bytes:
            return f"Sandbox input files exceed {self._max_input_bytes} bytes."
        return None

    @staticmethod
    def _validate_relative_path(relative_path: str) -> None:
        parts = relative_path.replace("\\", "/").split("/")
        if (
            not relative_path
            or relative_path.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError(f"Invalid sandbox input path: {relative_path}")
        if parts[0] == "main.py":
            raise ValueError("Input files must not overwrite main.py.")

    def _read_logs(self, container: Container, *, stderr: bool) -> tuple[str, bool]:
        raw = container.logs(stdout=not stderr, stderr=stderr)
        truncated = len(raw) > self._output_limit_bytes
        return raw[: self._output_limit_bytes].decode("utf-8", errors="replace"), truncated

    @staticmethod
    def _kill_quietly(container: Container) -> None:
        try:
            container.kill()
            container.wait(timeout=2)
        except (
            DockerException,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ):
            return

    @staticmethod
    def _remove_quietly(container: Container) -> None:
        try:
            container.remove(force=True)
        except NotFound:
            return
        except DockerException:
            return


def _encode_input_files(input_files: Mapping[str, str | bytes]) -> str:
    encoded: dict[str, str] = {}
    for relative_path, content in input_files.items():
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        encoded[relative_path] = base64.b64encode(raw).decode("ascii")
    payload = json.dumps(encoded, separators=(",", ":"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")
