import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("iee_copilot.api")


def error_body(code: str, message: str, details: Any = None) -> dict[str, dict[str, Any]]:
    return {"error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        status_code = exc.status_code
        code = "not_found" if status_code == 404 else "http_error"
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(
            status_code=status_code,
            content=error_body(code=code, message=message),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="validation_error",
                message="Request validation failed",
                details=jsonable_encoder(exc.errors()),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error at %s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_body(code="internal_server_error", message="Internal server error"),
        )
