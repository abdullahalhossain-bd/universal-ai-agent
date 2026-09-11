"""Redis-backed rate limiting for public customer endpoints.

Limits are shared across Render instances/workers.  The limiter uses the
trusted-proxy client-IP resolver and layered identities so a caller cannot
bypass the protection simply by rotating conversation IDs or visitor IDs.
"""

import hashlib

from fastapi import HTTPException, Request

from app.core.redis import redis_client
from app.core.security import resolve_client_ip


async def _hit(bucket: str, limit: int) -> bool:
    current = await redis_client.incr(bucket)
    if current == 1:
        await redis_client.expire(bucket, 60)
    return current > limit


async def enforce_customer_rate_limit(request: Request) -> None:
    path = request.url.path
    if not path.startswith("/v1/messages/customer/"):
        return

    peer = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = resolve_client_ip(peer, forwarded_for)

    api_key = request.headers.get("x-api-key", "")
    visitor_id = request.headers.get("x-visitor-id", "")
    api_identity = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:24] if api_key else "anonymous-key"
    visitor_identity = hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()[:24] if visitor_id else "anonymous-visitor"

    # State-changing customer requests are tighter; GET history/polling gets
    # a higher ceiling so normal chat UIs are not throttled unnecessarily.
    limit = 30 if request.method in {"POST", "PUT", "PATCH", "DELETE"} else 120
    endpoint = path.split("/", 4)[4] if len(path.split("/")) > 4 else "unknown"

    buckets = [
        (f"customer-rate:ip:{client_ip}", 120),
        (f"customer-rate:api:{api_identity}", 300),
        (f"customer-rate:visitor:{visitor_identity}", 60),
        (f"customer-rate:endpoint:{endpoint}", limit),
    ]

    try:
        for bucket, bucket_limit in buckets:
            if await _hit(bucket, bucket_limit):
                raise HTTPException(status_code=429, detail="Too many customer requests. Please try again shortly.")
    except HTTPException:
        raise
    except Exception:
        # Keep customer chat available if Redis has a transient outage. The
        # failure is intentionally isolated here rather than breaking requests.
        return
