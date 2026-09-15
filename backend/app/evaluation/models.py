from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.agent import AgentStatus

EvalCategory = Literal["orchestration", "guardrail"]


class EvalCheck(BaseModel):
    name: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)


class EvalCaseResult(BaseModel):
    case_id: str = Field(min_length=1)
    category: EvalCategory
    description: str
    passed: bool
    status: AgentStatus | None = None
    output: str | None = None
    duration_ms: float = Field(ge=0)
    step_count: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    failed_tool_calls: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    checks: list[EvalCheck] = Field(default_factory=list)


class EvalSummary(BaseModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    safety_pass_rate: float = Field(ge=0, le=1)
    total_tokens: int = Field(ge=0)
    total_tool_calls: int = Field(ge=0)
    failed_tool_calls: int = Field(ge=0)
    average_duration_ms: float = Field(ge=0)


class EvalReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: EvalSummary
    results: list[EvalCaseResult] = Field(default_factory=list)
