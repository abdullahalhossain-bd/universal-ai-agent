"""Loop-aware async Redis client.

`redis.asyncio` clients bind their connections to the event loop that
created them. A module-level singleton therefore breaks whenever the
process runs more than one loop over its lifetime (uvicorn reload
workers, test clients that spin a fresh loop per test, embedded
scenarios). Symptom: `RuntimeError: Event loop is closed` raised from
inside the redis connection pool.

`redis_client` below is a lightweight proxy that lazily creates ONE
underlying client per running event loop and delegates every attribute
to it. Production (a single long-lived loop) gets exactly the same
behaviour as before — one client, one pool — while secondary loops
always get a fresh, correctly-bound client.
"""

from __future__ import annotations

import asyncio
import weakref

import redis.asyncio as redis

from app.core.config import settings

# Same bounds as before: a hung Redis must fail fast so the fail-open
# paths in app/core/rate_limit.py can trigger promptly.
_CLIENT_KWARGS = dict(
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


class _LoopAwareRedis:
    """Delegate to a per-event-loop `redis.asyncio.Redis` instance."""

    def __init__(self) -> None:
        # WeakKeyDictionary so finished loops (tests, reloads) don't
        # leak their clients.
        self._clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, redis.Redis]" = (
            weakref.WeakKeyDictionary()
        )

    def _client_for_current_loop(self) -> redis.Redis:
        loop = asyncio.get_running_loop()
        client = self._clients.get(loop)
        if client is None:
            client = redis.from_url(settings.redis_url, **_CLIENT_KWARGS)
            self._clients[loop] = client
        return client

    def __getattr__(self, name: str):
        return getattr(self._client_for_current_loop(), name)


redis_client = _LoopAwareRedis()
