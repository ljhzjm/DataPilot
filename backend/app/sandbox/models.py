from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class SandboxExecutionKind(StrEnum):
    PYTHON = "python"
    DUCKDB = "duckdb"
    POSTGRES = "postgres"


class SandboxDatasetMount(BaseModel):
    dataset_id: UUID
    target_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )


class SandboxRequest(BaseModel):
    kind: SandboxExecutionKind
    code: str | None = None
    sql: str | None = None
    input_files: dict[str, str] = Field(default_factory=dict)
    data_mounts: list[SandboxDatasetMount] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, gt=0, le=60)

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.kind is SandboxExecutionKind.PYTHON and not self.code:
            raise ValueError("Python execution requires code.")
        if self.kind in {SandboxExecutionKind.DUCKDB, SandboxExecutionKind.POSTGRES}:
            if not self.sql:
                raise ValueError("SQL execution requires sql.")
            if self.input_files:
                raise ValueError("SQL execution does not accept input_files.")
            if self.data_mounts:
                raise ValueError("SQL execution does not accept data_mounts.")
        return self


class SandboxArtifact(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    mime_type: str = Field(min_length=1, max_length=128)
    size: int = Field(ge=0)
    content_base64: str

    @field_validator("path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            "\\" in value
            or ":" in value
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("Artifact path must be a safe relative path.")
        if path.suffix.casefold() not in {".csv", ".json", ".png"}:
            raise ValueError("Unsupported artifact type.")
        return path.as_posix()


class ExecutionResult(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    exit_code: int | None = None
    timed_out: bool = False
    duration_ms: float = Field(default=0, ge=0)
    artifacts: list[SandboxArtifact] = Field(default_factory=list)
