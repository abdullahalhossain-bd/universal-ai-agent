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
# Fixed 32-byte url-safe-base64 Fernet key, test-only — never reuse a
# committed key like this for a real environment.
os.environ.setdefault(
    "CREDENTIAL_ENCRYPTION_KEY",
    "1Q5CMAJ3S3iemRmjauMWsPLeJmpY-VPO0J_9jHijTxs=",
)

# Avoid IPv6 (::1) resolving to a different Postgres than Docker on 127.0.0.1
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

from tests.markers import (  # noqa: E402
    POSTGRES_AVAILABLE,
    REDIS_AVAILABLE,
    requires_postgres,
    requires_redis,
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
