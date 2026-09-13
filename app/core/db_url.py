"""Normalize merchant-provided database URLs to SQLAlchemy-callable form.

Merchants paste standard scheme URLs (mysql://, postgres://, mariadb://)
into dashboards and connection boxes. SQLAlchemy, however, requires a
driver-qualified dialect (mysql+pymysql://) or its canonical name
(postgresql://) — a bare `mysql://` resolves to the legacy MySQL-python
driver and fails with `ModuleNotFoundError: No module named 'MySQLdb'`,
and `postgres://` is rejected outright in SQLAlchemy 2.x.

Every call site that feeds a merchant-supplied connection_url into
create_engine() must pass it through normalize_database_url() first.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

# Bare scheme -> SQLAlchemy dialect that ships with the project's
# installed drivers (pymysql / psycopg2 / asyncpg).
_SCHEME_MAP = {
    "mysql": "mysql+pymysql",
    "mariadb": "mysql+pymysql",
    "postgres": "postgresql",
}


def normalize_database_url(url: str | None) -> str | None:
    """Return a SQLAlchemy-compatible copy of a merchant database URL.

    Leaves already driver-qualified schemes (mysql+pymysql://,
    postgresql+asyncpg://, ...), unknown schemes and non-URL strings
    untouched. Credentials inside the netloc are preserved byte-for-byte
    (a password containing %40 stays percent-encoded).
    """
    if not url or not isinstance(url, str):
        return url
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    scheme = (parts.scheme or "").lower()
    if "+" in scheme or scheme not in _SCHEME_MAP:
        return url
    return urlunsplit(
        (_SCHEME_MAP[scheme], parts.netloc, parts.path, parts.query, parts.fragment)
    )
