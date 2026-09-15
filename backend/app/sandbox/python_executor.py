import asyncio
import base64
import json
import mimetypes
import shutil
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from time import perf_counter, perf_counter_ns

import requests
from docker import DockerClient
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.types import Mount, Ulimit

from app.core.config import get_settings
from app.sandbox.models import ExecutionResult, SandboxArtifact, SandboxDatasetMount

_ALLOWED_ARTIFACT_SUFFIXES = {".csv", ".json", ".png"}
_MAX_DATASET_MOUNTS = 5


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
        dataset_volume: str | None = None,
        artifact_work_volume: str | None = None,
        artifact_work_root: Path | None = None,
        artifact_max_files: int | None = None,
        artifact_max_bytes: int | None = None,
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
        self._dataset_volume = dataset_volume or settings.sandbox_dataset_volume
        self._artifact_work_volume = (
            settings.sandbox_artifact_work_volume
            if artifact_work_volume is None
            else artifact_work_volume
        )
        self._artifact_work_root = (
            artifact_work_root or settings.sandbox_artifact_work_root
        ).resolve()
        self._artifact_max_files = artifact_max_files or settings.sandbox_artifact_max_files
        self._artifact_max_bytes = artifact_max_bytes or settings.sandbox_artifact_max_bytes

    async def close(self) -> None:
        if self._owns_client:
            self._client.close()

    async def execute(
        self,
        code: str,
        *,
        input_files: Mapping[str, str | bytes] | None = None,
        data_mounts: list[SandboxDatasetMount] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        validation_error = self._validate_payload(
            code,
            input_files or {},
            data_mounts or [],
        )
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
            data_mounts or [],
            effective_timeout,
        )

    def _execute_sync(
        self,
        code: str,
        input_files: Mapping[str, str | bytes],
        data_mounts: list[SandboxDatasetMount],
        effective_timeout: float,
    ) -> ExecutionResult:
        started = perf_counter()
        container: Container | None = None
        execution_id = f"execution-{perf_counter_ns()}"
        artifact_dir = self._artifact_work_root / execution_id

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
            artifact_dir.mkdir(parents=True, exist_ok=False)
            artifact_dir.chmod(0o777)
            environment = {
                "SANDBOX_CODE_B64": base64.b64encode(code.encode("utf-8")).decode("ascii"),
                "SANDBOX_FILES_B64": _encode_input_files(input_files),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "MPLBACKEND": "Agg",
                "MPLCONFIGDIR": "/tmp/matplotlib",  # noqa: S108
                "HOME": "/tmp",  # noqa: S108
            }
            output_mount = (
                Mount(
                    target="/workspace/outputs",
                    source=self._artifact_work_volume,
                    type="volume",
                    read_only=False,
                    subpath=execution_id,
                )
                if self._artifact_work_volume
                else Mount(
                    target="/workspace/outputs",
                    source=str(artifact_dir),
                    type="bind",
                    read_only=False,
                )
            )
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
                mounts=[
                    Mount(
                        target=f"/data/{mount.target_name}",
                        source=self._dataset_volume,
                        type="volume",
                        read_only=True,
                        subpath=str(mount.dataset_id),
                    )
                    for mount in data_mounts
                ]
                + [output_mount],
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

            try:
                artifacts = self._collect_artifacts(artifact_dir)
            except ValueError as exc:
                return ExecutionResult(
                    ok=False,
                    stdout=stdout,
                    stderr=f"Artifact validation failed: {exc}",
                    truncated=stdout_truncated or stderr_truncated,
                    exit_code=exit_code,
                    timed_out=timed_out,
                    duration_ms=(perf_counter() - started) * 1000,
                )
            return ExecutionResult(
                ok=not timed_out and exit_code == 0,
                stdout=stdout,
                stderr=stderr,
                truncated=stdout_truncated or stderr_truncated,
                exit_code=exit_code,
                timed_out=timed_out,
                duration_ms=(perf_counter() - started) * 1000,
                artifacts=artifacts,
            )
        except OSError as exc:
            return ExecutionResult(
                ok=False,
                stderr=f"Sandbox artifact workspace is unavailable: {exc}",
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
            shutil.rmtree(artifact_dir, ignore_errors=True)

    def _validate_payload(
        self,
        code: str,
        input_files: Mapping[str, str | bytes],
        data_mounts: list[SandboxDatasetMount],
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
        if len(data_mounts) > _MAX_DATASET_MOUNTS:
            return f"Sandbox supports at most {_MAX_DATASET_MOUNTS} dataset mounts."
        target_names = [mount.target_name for mount in data_mounts]
        if len(set(target_names)) != len(target_names):
            return "Sandbox dataset mount names must be unique."
        dataset_ids = [mount.dataset_id for mount in data_mounts]
        if len(set(dataset_ids)) != len(dataset_ids):
            return "Sandbox dataset mounts must reference unique datasets."
        return None

    def _collect_artifacts(self, artifact_dir: Path) -> list[SandboxArtifact]:
        artifacts: list[SandboxArtifact] = []
        total_bytes = 0
        for candidate in artifact_dir.rglob("*"):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            relative_path = _safe_artifact_path(candidate.relative_to(artifact_dir).as_posix())
            if Path(relative_path).suffix.casefold() not in _ALLOWED_ARTIFACT_SUFFIXES:
                continue
            size = candidate.stat().st_size
            if size > self._artifact_max_bytes - total_bytes:
                raise ValueError("Sandbox artifacts exceed configured limits.")
            content = candidate.read_bytes()
            total_bytes += len(content)
            if len(artifacts) >= self._artifact_max_files or total_bytes > self._artifact_max_bytes:
                raise ValueError("Sandbox artifacts exceed configured limits.")
            mime_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
            artifacts.append(
                SandboxArtifact(
                    path=relative_path,
                    mime_type=mime_type,
                    size=len(content),
                    content_base64=base64.b64encode(content).decode("ascii"),
                )
            )
        return artifacts

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


def _safe_artifact_path(value: str) -> str:
    path = PurePosixPath(value)
    parts = path.parts
    if parts and parts[0] == "outputs":
        parts = parts[1:]
    if (
        "\\" in value
        or ":" in value
        or path.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"Invalid sandbox artifact path: {value}")
    return Path(*parts).as_posix()
