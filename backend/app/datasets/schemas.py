from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.tools.duckdb_engine import ColumnInfo

DatasetStatus = Literal["processing", "ready", "failed"]


class DatasetView(BaseModel):
    id: UUID
    name: str
    original_filename: str
    table_name: str
    file_type: str
    file_size: int = Field(ge=0)
    status: DatasetStatus
    row_count: int | None = None
    columns: list[ColumnInfo] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DatasetSummary(BaseModel):
    id: UUID
    name: str
    original_filename: str
    table_name: str
    file_type: str
    file_size: int = Field(ge=0)
    status: DatasetStatus
    row_count: int | None = None
    created_at: datetime
    updated_at: datetime
