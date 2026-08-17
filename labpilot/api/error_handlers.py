from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from labpilot.api.errors import ApiError, GenerationUnavailable
from labpilot.api.schemas import AttemptOut, ErrorBody, ErrorEnvelope

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def error_response(
    request: Request,
    *,
    status: int,
    code: str,
    message: str,
    attempts: tuple = (),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or str(uuid4())
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            request_id=request_id,
            attempts=[
                AttemptOut(tier=one.tier, model=one.model, error=one.error)
                for one in attempts
            ],
        )
    )

    return JSONResponse(
        status_code=status,
        content=envelope.model_dump(),
        headers={REQUEST_ID_HEADER: request_id},
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    attempts = getattr(exc, "attempts", ())
    if isinstance(exc, GenerationUnavailable):
        logger.warning(
            "every tier failed: %s",
            "; ".join(f"{one.tier} {one.model}: {one.error}" for one in attempts),
        )

    return error_response(
        request,
        status=exc.status,
        code=exc.code,
        message=exc.message,
        attempts=attempts,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        request,
        status=422,
        code="invalid_request",
        message=_first_problem(exc),
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled request error",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"request_id": getattr(request.state, "request_id", None)},
    )

    return error_response(
        request,
        status=500,
        code="internal_error",
        message="an unexpected error occurred",
    )


def _first_problem(exc: RequestValidationError) -> str:
    problems = exc.errors()
    if not problems:
        return "the request could not be validated"

    first = problems[0]
    where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")

    return f"{where or 'request'}: {first.get('msg', 'is invalid')}"


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
