import asyncio
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.connectors.base.connector import Connector
from app.core.db_url import normalize_database_url
from app.discovery.scanners.sql_scanner import SQLSchemaScanner
from app.products.sql_identifier import validate_identifier
from app.schemas.product import UniversalProduct


class PostgreSQLConnector(Connector):
    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        url = make_url(normalize_database_url(connection_url))
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        self.engine = create_engine(url, pool_pre_ping=True)

    async def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def discover(self):
        return SQLSchemaScanner(self.connection_url).scan()

    def fetch_product_rows(self, table_name, columns, *, limit=200, offset=0):
        table = validate_identifier(table_name)
        safe_cols = [validate_identifier(c) for c in columns]
        if not safe_cols:
            return []
        col_sql = ", ".join(f'"{c}"' for c in safe_cols)
        sql = text(f'SELECT {col_sql} FROM "{table}" LIMIT :limit OFFSET :offset')
        with self.engine.connect() as conn:
            result = conn.execute(sql, {"limit": int(limit), "offset": int(offset)})
            return [dict(r._mapping) for r in result]

    def fetch_product_rows_incremental(self, table_name, columns, *, updated_column=None, created_column=None, id_column=None, watermark_at=None, watermark_id=None, limit=200, upper_bound=None):
        table = validate_identifier(table_name)
        safe_cols = [validate_identifier(c) for c in columns]
        if not safe_cols:
            return []
        ts = validate_identifier(updated_column or created_column) if (updated_column or created_column) else None
        ident = validate_identifier(id_column) if id_column else None
        col_sql = ", ".join(f'"{c}"' for c in safe_cols)
        params: dict[str, Any] = {"limit": int(limit)}
        predicates: list[str] = []
        if ts and watermark_at is not None:
            if ident and watermark_id is not None:
                predicates.append(f'("{ts}" > :watermark_at OR ("{ts}" = :watermark_at AND "{ident}" > :watermark_id))')
                params.update({"watermark_at": watermark_at, "watermark_id": watermark_id})
            else:
                predicates.append(f'"{ts}" > :watermark_at')
                params["watermark_at"] = watermark_at
        elif ident and watermark_id is not None:
            predicates.append(f'"{ident}" > :watermark_id')
            params["watermark_id"] = watermark_id
        if upper_bound is not None and ts:
            predicates.append(f'"{ts}" <= :upper_bound')
            params["upper_bound"] = upper_bound
        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        if ts and ident:
            order = f' ORDER BY "{ts}" ASC, "{ident}" ASC'
        elif ts:
            order = f' ORDER BY "{ts}" ASC'
        elif ident:
            order = f' ORDER BY "{ident}" ASC'
        else:
            order = ""
        sql = text(f'SELECT {col_sql} FROM "{table}"{where}{order} LIMIT :limit')
        with self.engine.connect() as conn:
            result = conn.execute(sql, params)
            return [dict(r._mapping) for r in result]

    def get_sync_watermark(self, table_name, timestamp_column=None, id_column=None, *, upper_bound=None):
        table = validate_identifier(table_name)
        ts = validate_identifier(timestamp_column) if timestamp_column else None
        ident = validate_identifier(id_column) if id_column else None
        bound = f' WHERE "{ts}" IS NOT NULL' if ts else ""
        params: dict[str, Any] = {}
        if ts and upper_bound is not None:
            bound += f' AND "{ts}" <= :upper_bound'
            params["upper_bound"] = upper_bound
        if ts and ident:
            sql = text(f'SELECT "{ts}" AS watermark_at, "{ident}" AS watermark_id FROM "{table}"{bound} ORDER BY "{ts}" DESC, "{ident}" DESC LIMIT 1')
        elif ts:
            sql = text(f'SELECT MAX("{ts}") AS watermark_at FROM "{table}"{bound}')
        elif ident:
            sql = text(f'SELECT MAX("{ident}") AS watermark_id FROM "{table}"')
        else:
            return {}
        with self.engine.connect() as conn:
            row = conn.execute(sql, params).first()
            return dict(row._mapping) if row else {}

    async def execute_query(self, sql: str, params: dict[str, Any] | None = None):
        def run_query():
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(r._mapping) for r in result]
        return await asyncio.to_thread(run_query)

    async def get_products(self, limit=50, offset=0) -> list[UniversalProduct]:
        raise NotImplementedError("Product mapping not configured — use fetch_product_rows with an explicit field mapping via ProductSyncService")

    async def get_product(self, product_id: str) -> UniversalProduct | None:
        raise NotImplementedError

    async def get_inventory(self, product_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def get_store_info(self) -> dict[str, Any]:
        raise NotImplementedError
