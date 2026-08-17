from __future__ import annotations

from fastapi import APIRouter, Request

from labpilot.api.config import ApiConfig
from labpilot.api.schemas import HealthResponse, RootResponse

router = APIRouter(tags=["service"])


@router.get("/", response_model=RootResponse, summary="What this service is")
def root() -> RootResponse:
    return RootResponse(
        name=ApiConfig.TITLE,
        version=ApiConfig.VERSION,
        docs="/docs",
    )


@router.get("/health", response_model=HealthResponse, summary="Readiness")
def health(request: Request) -> HealthResponse:
    # Counted once at startup, not per request: probing a provider would spend
    # quota, and a health check that costs money gets switched off.
    return HealthResponse(
        status="ok",
        version=ApiConfig.VERSION,
        providers_configured=len(request.app.state.providers),
    )
