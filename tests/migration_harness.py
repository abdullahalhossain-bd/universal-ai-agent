from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def create_scratch_schema(base_url: str) -> str:
    """Create an isolated schema and return a URL using it as search_path."""
    url = make_url(base_url)
    schema = f"migration_check_{uuid.uuid4().hex[:12]}"
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    finally:
        engine.dispose()

    scratch_url = url.update_query_dict(
        {"options": f"-csearch_path={schema},public"},
        append=True,
    )
    # str(url) masks the password with "***" (SQLAlchemy's default, meant
    # for safe logging) -- but this string is used to open a real
    # connection below, so it must keep the real password.
    return scratch_url.render_as_string(hide_password=False)


def drop_scratch_schema(scratch_url: str) -> None:
    """Drop the isolated migration schema, including all objects it owns."""
    url = make_url(scratch_url)
    options = url.query.get("options", "")
    marker = "-csearch_path="
    if marker not in options:
        return
    schema = options.split(marker, 1)[1].split(",", 1)[0]
    if not schema:
        return

    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        engine.dispose()
