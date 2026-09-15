from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.datasets.factory import build_dataset_service
from app.datasets.processor import DatasetProcessingError
from app.datasets.schemas import DatasetSummary, DatasetView
from app.datasets.service import DatasetService
from app.tools.duckdb_engine import QueryResult

router = APIRouter(prefix="/datasets", tags=["datasets"])


def get_dataset_service(request: Request) -> DatasetService:
    return build_dataset_service(request.app.state.analytics_engine)


@router.post(
    "/upload",
    response_model=DatasetView,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    file: Annotated[UploadFile, File()],
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> DatasetView:
    try:
        return await service.ingest(file.filename or "", file)
    except DatasetProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[DatasetSummary])
async def list_datasets(
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> list[DatasetSummary]:
    return await service.list_datasets()


@router.get("/{dataset_id}", response_model=DatasetView)
async def get_dataset(
    dataset_id: UUID,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> DatasetView:
    dataset = await service.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return dataset


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: UUID,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
) -> None:
    deleted = await service.delete_dataset(dataset_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")


@router.get("/{dataset_id}/preview", response_model=QueryResult)
async def preview_dataset(
    dataset_id: UUID,
    service: Annotated[DatasetService, Depends(get_dataset_service)],
    limit: int = 20,
) -> QueryResult:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Preview limit must be between 1 and 100.",
        )
    preview = await service.preview_dataset(dataset_id, limit=limit)
    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ready dataset not found.",
        )
    return preview
