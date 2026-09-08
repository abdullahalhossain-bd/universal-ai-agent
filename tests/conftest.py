"""
Shared pytest fixtures.

Sets required settings via env vars *before* app.main (and therefore
app.core.config.settings) is imported anywhere, since Settings() reads
the environment at import time. A dummy Postgres URL is enough to build
the SQLAlchemy engine without a real connection — engine creation does
not connect eagerly, only individual queries do.
"""

import os

# Prefer 127.0.0.1 to avoid IPv6 (::1) hitting a different local Postgres.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@127.0.0.1:5432/test_db",
)
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault("ALLOW_LOCAL_DATASOURCE_HOSTS", "true")
os.environ.setdefault(
    "CREDENTIAL_ENCRYPTION_KEY",
    "1Q5CMAJ3S3iemRmjauMWsPLeJmpY-VPO0J_9jHijTxs=",
)

if "DATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = (
        os.environ["DATABASE_URL"]
        .replace("@localhost:", "@127.0.0.1:")
        .replace("@localhost/", "@127.0.0.1/")
    )
if "REDIS_URL" in os.environ:
    os.environ["REDIS_URL"] = (
        os.environ["REDIS_URL"]
        .replace("//localhost:", "//127.0.0.1:")
        .replace("//localhost/", "//127.0.0.1/")
    )

import pytest
from fastapi.testclient import TestClient

from tests.markers import (
    POSTGRES_AVAILABLE,
    REDIS_AVAILABLE,
    requires_postgres,
    requires_redis,
)


@pytest.fixture(autouse=True)
def _no_signup_rate_limit(monkeypatch):
    """
    The dashboard-auth and billing tests perform many signups per run;
    the real signup limiter (5/hour per IP, fail-closed) would start
    returning 429 once the suite exceeds five signup calls in an hour,
    breaking unrelated tests. The limiter's own mechanics (Lua INCR,
    headers, fail-closed behaviour) are covered by
    tests/test_budget_security.py against real Redis, so the endpoint
    hook is neutralized here by default.
    """
    from app.api.routes import auth as auth_routes

    async def _allow(*args, **kwargs):
        return {"limit": 5, "remaining": 5, "reset": 0}

    monkeypatch.setattr(
        auth_routes, "enforce_signup_rate_limit", _allow
    )


@pytest.fixture(autouse=True)
def _schema_isolated_migration_harness(monkeypatch):
    """Run migration tests in throwaway schemas, not throwaway databases."""
    try:
        import tests.test_migrations as migration_tests
    except ImportError:
        return

    from tests.migration_harness import create_scratch_schema, drop_scratch_schema

    monkeypatch.setattr(
        migration_tests, "_create_scratch_db", create_scratch_schema
    )
    monkeypatch.setattr(
        migration_tests, "_drop_scratch_db",
        lambda _base_url, scratch_url: drop_scratch_schema(scratch_url),
    )


__all__ = [
    "POSTGRES_AVAILABLE",
    "REDIS_AVAILABLE",
    "requires_postgres",
    "requires_redis",
    "app",
    "client",
]


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c
