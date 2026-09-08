"""
Per-request observability middleware.

- Assigns (or honors an inbound) X-Request-ID and makes it available
  to every log line for the duration of the request via
  app.core.request_context.
- Emits one structured access-log line per request: method, path,
  status, duration, client IP. This is the "what actually happened
  in production" log — the thing you grep first when a merchant
  reports "the widget was broken at 3pm".
- Echoes the request ID back as a response header so it can be
  surfaced in error messages and matched against server logs when a
  merchant reports an issue.
"""

import logging
import time
import uuid

from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import set_request_id


access_logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:

        request_id = (
            request.headers.get("x-request-id") or str(uuid.uuid4())
        )
        set_request_id(request_id)

        client_ip = (
            request.client.host if request.client else None
        )

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # The global exception handlers in main.py convert this
            # into a 500 response — but by the time it gets there the
            # request_id contextvar has already served its purpose
            # here. Log the access line ourselves before re-raising
            # so a crash never means a silently missing access log.
            duration_ms = round(
                (time.perf_counter() - start) * 1000, 1
            )
            access_logger.error(
                "%s %s -> failed after %sms",
                request.method,
                request.url.path,
                duration_ms,
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        log_level = (
            logging.WARNING
            if response.status_code >= 500
            else logging.INFO
        )
        access_logger.log(
            log_level,
            "%s %s -> %s (%sms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "http_method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            },
        )

        return response
