import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


log = logging.getLogger("mission_lens.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def _resp(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return _resp(e.status, e.code, e.message, e.details)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError):
        details = [{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()]
        return _resp(422, "validation_error", "Invalid request", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        code = "not_found" if e.status_code == 404 else "http_error"
        return _resp(e.status_code, code, str(e.detail))

    @app.exception_handler(Exception)
    async def _any(req: Request, e: Exception):
        log.exception("unhandled error on %s %s", req.method, req.url.path)     # full traceback goes to the server log only
        return _resp(500, "internal_error", "Unexpected server error", {"type": type(e).__name__})
