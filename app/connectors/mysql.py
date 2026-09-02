"""
MySQL connector.

Accepts either individual connection parameters or a SQLAlchemy-style URL.
Product row fetch uses a synchronous SQLAlchemy engine for compatibility
with ProductSyncService batching.
"""

import asyncio
from typing import Any

try:
    import aiomysql
except ImportError:  # pragma: no cover
    aiomysql = None  # type: ignore

from sqlalchemy import create_engine, text

from app.products.sql_identifier import validate_identifier


def _parse_url(url: str) -> dict[str, Any]:
    from sqlalchemy.engine import make_url

    parsed = make_url(url)

    return {
        "host": parsed.host or "localhost",
        "port": parsed.port or 3306,
        "user": parsed.username or "",
        "password": parsed.password or "",
        "db": parsed.database or "",
    }


class MySQLConnector:
    """
    MySQL connector with test_connection and fetch_product_rows.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        *,
        connection_url: str | None = None,
    ):

        if connection_url:
            parsed = _parse_url(connection_url)
            host = host or parsed["host"]
            port = port or parsed["port"]
            username = username or parsed["user"]
            password = password or parsed["password"]
            database = database or parsed["db"]

        self.config = {
            "host": host,
            "port": port,
            "user": username,
            "password": password,
            "db": database,
        }

        self.connection_url = (
            connection_url
            or (
                f"mysql+pymysql://{username or ''}:"
                f"{password or ''}@{host or 'localhost'}:{port or 3306}/"
                f"{database or ''}"
            )
        )

        # Prefer pymysql for sync engine; fall back to the given URL as-is.
        sync_url = self.connection_url
        if sync_url.startswith("mysql+aiomysql://"):
            sync_url = "mysql+pymysql://" + sync_url[len("mysql+aiomysql://"):]
        elif sync_url.startswith("mysql://"):
            sync_url = "mysql+pymysql://" + sync_url[len("mysql://"):]

        self._engine = create_engine(sync_url, pool_pre_ping=True)

    async def test_connection(self) -> bool:
        if aiomysql is None:
            # Fall back to sync engine probe.
            try:
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return True
            except Exception:
                return False

        connection = await aiomysql.connect(**self.config)

        try:
            connection.close()
        except Exception:
            pass

        return True

    def fetch_product_rows(
        self,
        table_name: str,
        columns: list[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        table = validate_identifier(table_name)
        safe_cols = [validate_identifier(c) for c in columns]
        if not safe_cols:
            return []

        col_sql = ", ".join(f"`{c}`" for c in safe_cols)
        sql = text(
            f"SELECT {col_sql} FROM `{table}` "
            f"LIMIT :limit OFFSET :offset"
        )

        with self._engine.connect() as conn:
            result = conn.execute(
                sql,
                {"limit": int(limit), "offset": int(offset)},
            )
            return [dict(row._mapping) for row in result]

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a parameterized product query off the event loop."""

        def run_query() -> list[dict[str, Any]]:
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(row._mapping) for row in result]

        return await asyncio.to_thread(run_query)
