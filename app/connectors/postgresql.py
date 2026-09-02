import asyncio
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.connectors.base.connector import Connector
from app.discovery.scanners.sql_scanner import (
    SQLSchemaScanner,
)
from app.products.sql_identifier import validate_identifier
from app.schemas.product import (
    UniversalProduct,
)


class PostgreSQLConnector(Connector):

    def __init__(
        self,
        connection_url: str,
    ):
        self.connection_url = connection_url

        url = make_url(connection_url)

        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")

        self.engine = create_engine(
            url,
            pool_pre_ping=True,
        )

    async def test_connection(self) -> bool:

        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            return True

        except Exception:
            return False

    async def discover(self):

        scanner = SQLSchemaScanner(
            self.connection_url
        )

        return scanner.scan()

    def fetch_product_rows(
        self,
        table_name: str,
        columns: list[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Synchronous page fetch used by ProductSyncService.

        Identifiers are validated against a strict pattern to prevent
        SQL injection via table/column names.
        """
        table = validate_identifier(table_name)
        safe_cols = [validate_identifier(c) for c in columns]

        if not safe_cols:
            return []

        col_sql = ", ".join(f'"{c}"' for c in safe_cols)

        sql = text(
            f'SELECT {col_sql} FROM "{table}" '
            f"LIMIT :limit OFFSET :offset"
        )

        with self.engine.connect() as conn:
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
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(row._mapping) for row in result]

        return await asyncio.to_thread(run_query)

    async def get_products(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UniversalProduct]:

        raise NotImplementedError(
            "Product mapping not configured — use fetch_product_rows "
            "with an explicit field mapping via ProductSyncService"
        )

    async def get_product(
        self,
        product_id: str,
    ) -> UniversalProduct | None:

        raise NotImplementedError

    async def get_inventory(
        self,
        product_id: str,
    ) -> dict[str, Any]:

        raise NotImplementedError

    async def get_store_info(
        self,
    ) -> dict[str, Any]:

        raise NotImplementedError