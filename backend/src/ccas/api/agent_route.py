"""Route class for REST routes backed by Agent query services.

Agent query errors on these routes use the same public projection as MCP and
CLI (``services.query_errors``), in the project envelope ``{success, message,
data}``:

- :class:`AgentQueryError` → its public message, status 404 / 422 / 500 by code.
- Any other unexpected exception → ``public_unexpected_error``, status 500,
  never the exception text.

Only the bills, transactions, budgets and pipeline routers use this class:
they are the only REST modules that call Agent query services, and the Agent
wording would mislead on other routes, which keep FastAPI's defaults. HTTP
errors and request validation errors are re-raised to their app-level handlers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from ccas.api.schemas import ErrorResponse
from ccas.services.query_errors import (
    AgentQueryError,
    public_query_error,
    public_unexpected_error,
)

logger = logging.getLogger(__name__)

_STATUS_BY_CODE: dict[str, int] = {
    "resource_not_found": 404,
    "invalid_argument": 422,
}


class AgentQueryRoute(APIRoute):
    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        path = self.path

        async def _run(request: Request) -> Response:
            try:
                return await handler(request)
            except (StarletteHTTPException, RequestValidationError):
                raise
            except AgentQueryError as exc:
                return _error_response(
                    _STATUS_BY_CODE.get(exc.code, 500), public_query_error(exc)
                )
            except Exception as exc:
                # Never log the exception object: it may carry SQL, bound
                # parameters or database values.
                logger.error(
                    "Agent REST route failed: %s (%s)", path, type(exc).__name__
                )
                return _error_response(500, public_unexpected_error(exc))

        return _run


def _error_response(status: int, payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(message=payload["message"]).model_dump(),
    )
