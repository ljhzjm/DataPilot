from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class SandboxExecutionKind(StrEnum):
    PYTHON = "python"
    DUCKDB = "duckdb"
    POSTGRES = "postgres"


class SandboxRequest(BaseModel):
    kind: SandboxExecutionKind
    code: str | None = None
    sql: str | None = None
    input_files: dict[str, str] = Field(default_factory=dict)
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
        return self


class ExecutionResult(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    exit_code: int | None = None
    timed_out: bool = False
    duration_ms: float = Field(default=0, ge=0)
