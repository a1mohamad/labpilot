from fastapi import APIRouter

from labpilot.api.routers import compare, health

# /health and / stay off the version prefix: an orchestrator's probe must not
# have to know which API version is deployed.
service_router = APIRouter()
service_router.include_router(health.router)

api_router = APIRouter()
api_router.include_router(compare.router)

__all__ = [
    "api_router",
    "service_router",
]
