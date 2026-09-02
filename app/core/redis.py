import redis.asyncio as redis

from app.core.config import settings


redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    # Without these, a Redis that's hung (not just refusing
    # connections outright — e.g. a stuck failover, network
    # black hole) leaves calls blocking with no bound. That
    # stalls every chat request until the OS-level TCP
    # timeout kicks in, which can be minutes. Bounding both
    # the initial connect and each command lets the
    # rate_limit fail-open path in app/core/rate_limit.py
    # actually trigger promptly instead of hanging first.
    socket_connect_timeout=2,
    socket_timeout=2,
)
