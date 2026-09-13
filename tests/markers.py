"""
Shared pytest skip markers for optional external services.

Import these in integration tests instead of reaching into conftest
(which pytest loads specially and should not be treated as a normal module).
"""

from __future__ import annotations

import os

import pytest

# Prefer 127.0.0.1 over "localhost" so Windows/macOS do not hit a different
# Postgres on ::1 (IPv6) than the Docker-mapped instance on IPv4.
_DEFAULT_DATABASE_URL = "postgresql://user:pass@127.0.0.1:5432/test_db"
_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    # Normalize localhost -> 127.0.0.1 to avoid IPv6 auth surprises.
    return url.replace("@localhost:", "@127.0.0.1:").replace(
        "@localhost/", "@127.0.0.1/"
    )


def redis_url() -> str:
    url = os.environ.get("REDIS_URL", _DEFAULT_REDIS_URL)
    return url.replace("//localhost:", "//127.0.0.1:").replace(
        "//localhost/", "//127.0.0.1/"
    )


def postgres_reachable() -> tuple[bool, str]:
    """Return (ok, detail). detail is empty on success, else the error text."""
    url = database_url()
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def redis_reachable() -> tuple[bool, str]:
    url = redis_url()
    try:
        import redis as redis_sync

        client = redis_sync.from_url(url, socket_connect_timeout=1)
        client.ping()
        client.close()
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# Evaluated at import (collection). Fixtures also re-check at runtime.
_pg_ok, _pg_err = postgres_reachable()
_redis_ok, _redis_err = redis_reachable()

POSTGRES_AVAILABLE = _pg_ok
REDIS_AVAILABLE = _redis_ok

_pg_reason = (
    "PostgreSQL not reachable / auth failed for DATABASE_URL "
    f"({database_url()}). {_pg_err} "
    "Fix: docker run -d --name uaa-pg -e POSTGRES_USER=user "
    "-e POSTGRES_PASSWORD=pass -e POSTGRES_DB=test_db -p 5432:5432 postgres:16 "
    "&& alembic upgrade head. Or set DATABASE_URL to match your instance."
)

_redis_reason = (
    "Redis not reachable at REDIS_URL "
    f"({redis_url()}). {_redis_err} "
    "Fix: docker run -d --name uaa-redis -p 6379:6379 redis:7"
)

requires_postgres = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=_pg_reason)
requires_redis = pytest.mark.skipif(not REDIS_AVAILABLE, reason=_redis_reason)


def skip_unless_postgres() -> None:
    """Call inside a fixture for a runtime re-check (more reliable than import-time)."""
    ok, err = postgres_reachable()
    if not ok:
        pytest.skip(
            "PostgreSQL not reachable / auth failed for DATABASE_URL "
            f"({database_url()}). {err} "
            "Fix credentials or start: docker run -d --name uaa-pg "
            "-e POSTGRES_USER=user -e POSTGRES_PASSWORD=pass "
            "-e POSTGRES_DB=test_db -p 5432:5432 postgres:16"
        )


def skip_unless_redis() -> None:
    ok, err = redis_reachable()
    if not ok:
        pytest.skip(
            "Redis not reachable at "
            f"{redis_url()}. {err}"
        )
