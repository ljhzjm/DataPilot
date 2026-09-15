from typing import Any, Literal

from pydantic import BaseModel, Field


class FunctionDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class ToolError(BaseModel):
    code: str
    message: str = Field(min_length=1)
