from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ArtifactView(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    size: int = Field(ge=0)
    url: str
    created_at: datetime
