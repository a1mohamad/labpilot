from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from labpilot.api.config import ApiConfig
from labpilot.api.error_handlers import register_error_handlers
from labpilot.api.middleware.body_limit import RequestBodyLimitMiddleware
from labpilot.api.middleware.request_id import RequestIDMiddleware
from labpilot.api.routers import api_router, service_router
from labpilot.api.startup import validate_provider_keys
from labpilot.llm import LLMClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail at boot, not on the first request. Without this the server starts
    # happily with no API keys and answers 503 forever, which is
    # indistinguishable from every provider being down.
    providers = validate_provider_keys()
    logger.info("%d of the chain's tiers have a key", len(providers))

    app.state.providers = providers
    app.state.client = LLMClient()

    try:
        yield
    finally:
        del app.state.client
        del app.state.providers


def create_app() -> FastAPI:
    application = FastAPI(
        title=ApiConfig.TITLE,
        summary=ApiConfig.SUMMARY,
        version=ApiConfig.VERSION,
        lifespan=lifespan,
    )

    # Middleware runs outermost-last, so request ID is added last and therefore
    # wraps everything: a body rejected for size still carries a correlation ID.
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=ApiConfig.MAX_REQUEST_BODY_BYTES,
    )
    if ApiConfig.CORS_ALLOW_ORIGINS:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(ApiConfig.CORS_ALLOW_ORIGINS),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
    application.add_middleware(RequestIDMiddleware)

    register_error_handlers(application)
    application.include_router(service_router)
    application.include_router(api_router, prefix=ApiConfig.PREFIX)

    # Optional: the container ships it, a bare API deployment need not.
    if ApiConfig.FRONTEND_DIR.is_dir():
        application.mount(
            "/ui",
            StaticFiles(directory=ApiConfig.FRONTEND_DIR, html=True),
            name="ui",
        )

    return application


app = create_app()
