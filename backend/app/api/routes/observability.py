from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.session import AsyncSessionLocal
from app.observability.schemas import TraceView, UsagePage, UsageSummary
from app.observability.service import ObservabilityService

router = APIRouter(prefix="/observability", tags=["observability"])


def get_observability_service() -> ObservabilityService:
    return ObservabilityService(AsyncSessionLocal)


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    service: Annotated[ObservabilityService, Depends(get_observability_service)],
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    conversation_id: UUID | None = None,
) -> UsageSummary:
    return await service.summary(
        start_at=start_at,
        end_at=end_at,
        conversation_id=conversation_id,
    )


@router.get("/usage", response_model=UsagePage)
async def usage_records(
    service: Annotated[ObservabilityService, Depends(get_observability_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    conversation_id: UUID | None = None,
) -> UsagePage:
    return await service.list_usage(
        limit=limit,
        offset=offset,
        start_at=start_at,
        end_at=end_at,
        conversation_id=conversation_id,
    )


@router.get("/traces/{trace_id}", response_model=TraceView)
async def trace_detail(
    trace_id: UUID,
    service: Annotated[ObservabilityService, Depends(get_observability_service)],
) -> TraceView:
    trace = await service.get_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found.",
        )
    return trace
