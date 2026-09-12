"""Redis-backed rate limiting for public customer endpoints.

Limits are shared across Render instances/workers. The limiter uses the
trusted-proxy client-IP resolver and layered identities so a caller cannot
bypass protection simply by rotating conversation IDs or visitor IDs.
"""

import hashlib
import logging

from fastapi import HTTPException, Request

from app.core.redis import redis_client
from app.core.security import resolve_client_ip

logger = logging.getLogger(__name__)

# INCR + EXPIRE must be one atomic operation. Otherwise a worker crash between
# the two commands can leave a permanent bucket in Redis and silently disable
# the intended rate limit for that identity.
_HIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def _hit(bucket: str, limit: int, window_seconds: int = 60) -> bool:
    current = await redis_client.eval(_HIT_SCRIPT, 1, bucket, window_seconds)
    return int(current) > limit


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
    except Exception as exc:
        # A state-changing public request can trigger paid LLM/vision work, so
        # failing open on Redis outage creates an avoidable cost-abuse path.
        # Reads may remain available for resilience, but mutations fail closed.
        logger.exception("Customer rate limiter unavailable: %s", exc)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            raise HTTPException(status_code=503, detail="Customer request protection is temporarily unavailable. Please retry shortly.") from exc
        return
