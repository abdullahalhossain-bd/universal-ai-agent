"""Single source of truth for bounded sync retry policy."""
from __future__ import annotations
import asyncio
import os
import random

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None
try:
    from sqlalchemy.exc import DBAPIError, OperationalError
except ImportError:  # pragma: no cover
    DBAPIError = OperationalError = ()

MAX_ATTEMPTS = max(1, min(int(os.getenv("SYNC_MAX_ATTEMPTS", "4")), 8))
BASE_DELAY = max(0.1, float(os.getenv("SYNC_RETRY_BASE_DELAY", "1.0")))
MAX_DELAY = max(BASE_DELAY, float(os.getenv("SYNC_RETRY_MAX_DELAY", "15.0")))


def is_transient_sync_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, asyncio.TimeoutError)):
        return True
    if httpx is not None and isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, (OperationalError, DBAPIError)):
        return bool(getattr(exc, "connection_invalidated", True))
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status == 429 or (isinstance(status, int) and 500 <= status < 600)


def retry_delay(attempt: int) -> float:
    attempt = max(1, int(attempt))
    delay = min(MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1)))
    return delay * (0.75 + random.random() * 0.5)


async def run_with_retry(operation, *, attempts: int = MAX_ATTEMPTS, base_delay: float = BASE_DELAY, max_delay: float = MAX_DELAY, logger=None):
    """Retry only transient failures; queue workers use the same policy constants."""
    attempts = max(1, min(int(attempts), 8))
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not is_transient_sync_error(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay *= 0.75 + random.random() * 0.5
            if logger:
                logger.warning("transient sync failure; retry=%s/%s delay=%.2fs error=%s", attempt, attempts - 1, delay, exc)
            await asyncio.sleep(delay)
    raise last_exc
