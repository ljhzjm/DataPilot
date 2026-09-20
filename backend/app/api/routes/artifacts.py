import asyncio
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.dependencies import get_workspace_id
from app.artifacts.service import ArtifactService
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def get_artifact_service() -> ArtifactService:
    return ArtifactService(AsyncSessionLocal)


@router.get("/{artifact_id}")
async def download_artifact(
    artifact_id: UUID,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
    workspace_id: Annotated[UUID, Depends(get_workspace_id)],
) -> FileResponse:
    artifact = await service.get(workspace_id, artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found.",
        )
    path = Path(artifact.stored_path)
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact file is missing.",
        )
    return FileResponse(
        path,
        media_type=artifact.mime_type,
        filename=artifact.filename,
    )
