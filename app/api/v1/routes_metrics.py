from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.models.api.responses import SystemMetricsResponse
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics(
    _: str | None = Depends(verify_api_key),
) -> SystemMetricsResponse:
    service = MetricsService()
    metrics = await service.get_system_metrics()
    return SystemMetricsResponse(**metrics.model_dump(), api_version="v1")
