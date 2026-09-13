"""
Per-request correlation ID.

Set once per request by RequestContextMiddleware (app/core/middleware.py)
and read anywhere — including deep in service/worker code that has no
access to the FastAPI `Request` object — so every log line emitted while
handling a request can be tied back to that request.

Uses contextvars rather than a global so concurrent requests handled by
the same async worker never leak each other's IDs.
"""

import contextvars

_request_id_ctx: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar("request_id", default=None)
)


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()
