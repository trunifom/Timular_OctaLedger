"""Loopback HTTP application: context, middleware and error mapping.

Responsibility
--------------
Assemble the FastAPI application from an :class:`AppContext` (all services and the token):

* **Middleware** rejects requests with a foreign ``Host``/``Origin`` (``api.security``) and
  oversized bodies *before* any route runs.
* **Error mapping** turns every :class:`OctaLedgerError` into a JSON error with a stable code, a
  German user message and a fitting HTTP status; unexpected exceptions become a generic 500
  **without** stack trace or internals (details go to the log only).
* Interactive documentation endpoints are disabled to keep the attack surface minimal.

Routes live in :mod:`octaledger.api.routes`; the uvicorn server is started by the agent.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from octaledger import __version__
from octaledger.api.context import AgentControl, AppContext
from octaledger.api.routes import build_router
from octaledger.api.schemas import API_PREFIX
from octaledger.api.security import check_request_origin
from octaledger.core.errors import (
    ApiUnavailableError,
    AuthenticationError,
    BleConnectionError,
    ConfigurationError,
    ConflictError,
    DataIntegrityError,
    ForbiddenOriginError,
    ImportDataError,
    IntegrationError,
    InvalidStateError,
    NotFoundError,
    OctaLedgerError,
    UnsupportedDeviceError,
    ValidationError,
)

logger = logging.getLogger(__name__)

#: Largest accepted request body (a backup restore carries the whole backup).
MAX_BODY_BYTES = 64 * 1024 * 1024

#: HTTP status per error class (most specific first).
_STATUS: tuple[tuple[type[OctaLedgerError], int], ...] = (
    (AuthenticationError, 401),
    (ForbiddenOriginError, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (InvalidStateError, 409),
    (ValidationError, 422),
    (ConfigurationError, 422),  # invalid settings entered by the user are fixable
    (UnsupportedDeviceError, 422),
    (ImportDataError, 422),
    (BleConnectionError, 502),
    (IntegrationError, 502),  # also IntegrationConnectionError: the target failed, not us
    (ApiUnavailableError, 503),
    (DataIntegrityError, 500),
)


def status_for(error: OctaLedgerError) -> int:
    """Return the HTTP status for an OctaLedger error."""
    for error_class, status in _STATUS:
        if isinstance(error, error_class):
            return status
    return 500


def error_response(error: OctaLedgerError) -> JSONResponse:
    """Build the uniform JSON error body ``{"error": {...}}``."""
    return JSONResponse({"error": error.to_dict()}, status_code=status_for(error))


def create_app(context: AppContext) -> FastAPI:
    """Create the FastAPI application for ``context``.

    Args:
        context: Services, token and port.

    Returns:
        The configured application (docs/openapi endpoints disabled).
    """
    app = FastAPI(
        title="OctaLedger local API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Reject foreign hosts/origins and oversized bodies before routing."""
        try:
            check_request_origin(
                request.headers.get("host"), request.headers.get("origin"), context.port
            )
        except ForbiddenOriginError as exc:
            logger.warning("Rejected request: %s", exc.details.get("reason"))
            return error_response(exc)
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
            return JSONResponse(
                {
                    "error": ValidationError(
                        "Request body too large",
                        user_message="Die Anfrage ist zu groß.",
                    ).to_dict()
                },
                status_code=413,
            )
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(OctaLedgerError)
    async def handle_octaledger_error(_request: Request, exc: OctaLedgerError) -> JSONResponse:
        """Map an OctaLedger error to its HTTP status and the uniform error body."""
        level = logging.ERROR if status_for(exc) >= 500 else logging.INFO
        logger.log(level, "API error %s", exc)
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Turn a request validation problem into a uniform 422 naming the offending fields."""
        fields = sorted(
            {".".join(str(p) for p in err["loc"][1:]) or "Anfrage" for err in exc.errors()}
        )
        return error_response(
            ValidationError(
                f"Invalid request: {fields}",
                user_message=f"Ungültige Eingabe in: {', '.join(fields)}.",
                details={"fields": fields},
            )
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        """Last resort: log the traceback, answer with a generic 500 that reveals no internals."""
        logger.exception("Unhandled error in API route")
        return error_response(OctaLedgerError(f"Unexpected {type(exc).__name__}"))

    app.include_router(build_router(context), prefix=API_PREFIX)
    return app


__all__ = ["AgentControl", "AppContext", "create_app", "error_response", "status_for"]
