import hashlib
import logging
import time

import redis.exceptions as redis_exceptions
from fastapi import HTTPException

from app.core.redis import redis_client

logger = logging.getLogger("app.rate_limit")

PLAN_RATE_LIMITS = {
    "starter": {"store": 30, "ip": 10},
    "growth": {"store": 100, "ip": 30},
    "pro": {"store": 300, "ip": 100},
}

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
    *, key: str, limit: int, label: str, window_ttl: int = 61,
    fail_closed: bool = False,
) -> dict:
    try:
        result = await redis_client.eval(_RATE_LIMIT_LUA, 1, key, window_ttl)
    except redis_exceptions.RedisError:
        if fail_closed:
            logger.error("Redis unavailable for fail-closed rate limit label=%s", label, exc_info=True)
            raise HTTPException(
                status_code=503,
                detail="Rate limiting service temporarily unavailable",
                headers={"Retry-After": "30"},
            )
        logger.error("Redis unavailable for rate limit key=%s; failing open", key, exc_info=True)
        return {"limit": limit, "remaining": limit, "reset": int(time.time()) + window_ttl}

    count = int(result[0])
    ttl = max(int(result[1]), 0)
    reset_at = int(time.time()) + ttl
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"{label} rate limit exceeded. Maximum {limit} requests per minute.",
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
            },
        )
    return {"limit": limit, "remaining": max(limit - count, 0), "reset": reset_at}


async def enforce_rate_limit(*, store_id: str, plan: str, client_ip: str) -> dict:
    plan_name = (plan or "starter").lower().strip()
    limits = PLAN_RATE_LIMITS.get(plan_name, PLAN_RATE_LIMITS["starter"])
    window = int(time.time() // 60)
    store_result = await _check_limit(
        key=f"rate_limit:store:{store_id}:minute:{window}",
        limit=limits["store"], label="Store",
    )
    ip_result = await _check_limit(
        key=f"rate_limit:ip:{client_ip}:store:{store_id}:minute:{window}",
        limit=limits["ip"], label="IP",
    )
    return {"store": store_result, "ip": ip_result}


async def enforce_knowledge_rate_limit(*, store_id: str, plan: str) -> dict:
    """Store-scoped limiter for the knowledge search endpoints.

    These routes can trigger full-table tsvector/ILIKE scans and (with
    pgvector) a semantic model encode, so a single store must not be able
    to submit unbounded concurrent searches. This bucket is separate from
    the chat limiter so knowledge usage does not consume chat budget.
    """
    plan_name = (plan or "starter").lower().strip()
    limits = PLAN_RATE_LIMITS.get(plan_name, PLAN_RATE_LIMITS["starter"])
    window = int(time.time() // 60)
    return await _check_limit(
        key=f"rate_limit:knowledge:{store_id}:minute:{window}",
        limit=limits["store"], label="Knowledge search",
    )


async def enforce_signup_rate_limit(*, client_ip: str) -> dict:
    """Bound unauthenticated tenant/key creation by source IP."""
    window = int(time.time() // 3600)
    return await _check_limit(
        key=f"rate_limit:signup:ip:{client_ip}:hour:{window}",
        limit=5, label="Signup", window_ttl=3601, fail_closed=True,
    )


async def enforce_login_rate_limit(*, client_ip: str, email: str, admin: bool = False) -> dict:
    """Fail-closed protection against credential stuffing/brute force.

    The email is hashed before becoming part of the Redis key, so raw
    account identifiers are never stored in the rate-limit keyspace.
    Two independent buckets are enforced: source IP and account email.
    """
    prefix = "admin_login" if admin else "login"
    normalized = email.strip().lower()
    email_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    window = int(time.time() // 60)
    ip_result = await _check_limit(
        key=f"rate_limit:{prefix}:ip:{client_ip}:minute:{window}",
        limit=10, label="Admin login IP" if admin else "Login IP",
        fail_closed=True,
    )
    account_result = await _check_limit(
        key=f"rate_limit:{prefix}:account:{email_hash}:minute:{window}",
        limit=5, label="Admin login account" if admin else "Login account",
        fail_closed=True,
    )
    return {"ip": ip_result, "account": account_result}
