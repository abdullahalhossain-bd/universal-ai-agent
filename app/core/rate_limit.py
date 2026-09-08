import logging
import time

import redis.exceptions as redis_exceptions
from fastapi import HTTPException

from app.core.redis import redis_client

logger = logging.getLogger("app.rate_limit")


PLAN_RATE_LIMITS = {
    "starter": {
        "store": 30,
        "ip": 10,
    },
    "growth": {
        "store": 100,
        "ip": 30,
    },
    "pro": {
        "store": 300,
        "ip": 100,
    },
}


# ---------------------------------
# Atomic fixed-window counter
# ---------------------------------
#
# INCR + EXPIRE as two separate round-trips is not
# atomic: a client that crashes between the two (or a
# connection drop at the wrong moment) can leave the
# counter key without a TTL. This Lua script performs
# INCR and EXPIRE server-side as one indivisible
# operation, guaranteeing every counter key always
# carries a TTL.
#
# KEYS[1] = counter key
# ARGV[1] = window TTL in seconds
#
# Returns { count, ttl }.

_RATE_LIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


async def _check_limit(
    *,
    key: str,
    limit: int,
    label: str,
    window_ttl: int = 61,
    fail_closed: bool = False,
) -> dict:
    try:
        result = await redis_client.eval(
            _RATE_LIMIT_LUA,
            1,
            key,
            window_ttl,
        )
    except redis_exceptions.RedisError:
        if fail_closed:
            logger.error(
                "Redis unavailable while checking fail-closed rate limit "
                "for label=%s",
                label,
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail="Rate limiting service temporarily unavailable",
                headers={"Retry-After": "30"},
            )

        # Fail OPEN: Redis being down should degrade rate
        # limiting, not take down the whole chat product.
        # Every chat request funnels through this call, so
        # any exception here (connection refused, timeout,
        # cluster failover, etc.) would otherwise 500 every
        # request until Redis recovers. We log loudly so the
        # outage is visible, and let the request through
        # un-limited rather than block real traffic.
        logger.error(
            "Redis unavailable while checking rate limit "
            "for key=%s (%s) — failing open, request "
            "allowed without a count.",
            key,
            label,
            exc_info=True,
        )
        return {
            "limit": limit,
            "remaining": limit,
            "reset": int(time.time()) + window_ttl,
        }

    # redis-py (decode_responses=True) returns a list
    # of ints here: [count, ttl].
    count = int(result[0])
    ttl = int(result[1])

    if ttl < 0:
        ttl = window_ttl

    remaining = max(
        limit - count,
        0,
    )

    reset_at = (
        int(time.time())
        + ttl
    )

    if count > limit:

        raise HTTPException(
            status_code=429,
            detail=(
                f"{label} rate limit exceeded. "
                f"Maximum {limit} requests "
                "per minute."
            ),
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(
                    limit
                ),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(
                    reset_at
                ),
            },
        )

    return {
        "limit": limit,
        "remaining": remaining,
        "reset": reset_at,
    }


async def enforce_rate_limit(
    *,
    store_id: str,
    plan: str,
    client_ip: str,
) -> dict:

    plan_name = (
        plan or "starter"
    ).lower().strip()

    limits = PLAN_RATE_LIMITS.get(
        plan_name,
        PLAN_RATE_LIMITS["starter"],
    )

    window = int(
        time.time() // 60
    )

    # ---------------------------------
    # Store limit
    # ---------------------------------

    store_key = (
        f"rate_limit:"
        f"store:{store_id}:"
        f"minute:{window}"
    )

    store_result = await _check_limit(
        key=store_key,
        limit=limits["store"],
        label="Store",
    )

    # ---------------------------------
    # IP limit
    # ---------------------------------

    ip_key = (
        f"rate_limit:"
        f"ip:{client_ip}:"
        f"store:{store_id}:"
        f"minute:{window}"
    )

    ip_result = await _check_limit(
        key=ip_key,
        limit=limits["ip"],
        label="IP",
    )

    return {
        "store": store_result,
        "ip": ip_result,
    }


async def enforce_signup_rate_limit(*, client_ip: str) -> dict:
    """Bound unauthenticated tenant/key creation by source IP."""

    window = int(time.time() // 3600)
    return await _check_limit(
        key=f"rate_limit:signup:ip:{client_ip}:hour:{window}",
        limit=5,
        label="Signup",
        window_ttl=3601,
        fail_closed=True,
    )