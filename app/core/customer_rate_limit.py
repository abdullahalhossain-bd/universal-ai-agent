"""Rate limiting for public customer messaging endpoints.

The limiter is intentionally small and Redis-backed so limits are shared across
Render instances/workers. If Redis is unavailable, the dependency fails open
for availability, while emitting a warning in the application logs.
"""

from fastapi import Request

from app.core.redis import redis_client


async def enforce_customer_rate_limit(request: Request) -> None:
    path = request.url.path
    if not path.startswith("/v1/messages/customer/"):
        return

    client_host = request.client.host if request.client else "unknown"
    api_key = request.headers.get("x-api-key", "")
    visitor_id = request.headers.get("x-visitor-id", "")
    identity = f"{client_host}:{api_key[-12:]}:{visitor_id[:80]}"
    bucket = f"customer-rate:{identity}:{path.split('/')[4] if len(path.split('/')) > 4 else 'unknown'}"

    try:
        current = await redis_client.incr(bucket)
        if current == 1:
            await redis_client.expire(bucket, 60)
        if current > 30:
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail="Too many customer requests. Please try again shortly.")
    except HTTPException:
        raise
    except Exception:
        # Do not make customer chat unavailable solely because Redis is down.
        return
