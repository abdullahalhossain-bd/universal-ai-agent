"""
MySQL connector with safe product reads and incremental synchronization.
"""

import asyncio
from typing import Any

try:
    import aiomysql
except ImportError:
    aiomysql = None  # type: ignore

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from app.discovery.scanners.sql_scanner import SQLSchemaScanner
from app.products.sql_identifier import validate_identifier


def _parse_url(url):
    parsed = make_url(url)
    return {"host": parsed.host or "localhost", "port": parsed.port or 3306, "user": parsed.username or "", "password": parsed.password or "", "db": parsed.database or ""}


def _build_sync_url(*, host, port, username, password, database):
    return URL.create(drivername="mysql+pymysql", username=username or "", password=password or "", host=host or "localhost", port=port or 3306, database=database or "")


class MySQLConnector:
    # Bounded merchant-DB execution (see postgresql.py): connect/read/write
    # timeouts stop a hung merchant database from blocking the sync worker.
    _CONNECT_TIMEOUT_S = 10
    _READ_TIMEOUT_S = 60

    def __init__(self, host=None, port=None, username=None, password=None, database=None, *, connection_url=None):
        if connection_url:
            parsed = _parse_url(connection_url)
            host = host or parsed["host"]; port = port or parsed["port"]; username = username or parsed["user"]; password = password or parsed["password"]; database = database or parsed["db"]
        self.config = {"host": host, "port": port, "user": username, "password": password, "db": database}
        self._engine = create_engine(
            _build_sync_url(host=host, port=port, username=username, password=password, database=database),
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": self._CONNECT_TIMEOUT_S,
                "read_timeout": self._READ_TIMEOUT_S,
                "write_timeout": 30,
            },
        )

    def dispose(self):
        """Release pooled merchant connections (call when done with the job)."""
        self._engine.dispose()

    def discover(self):
        """Return the live database schema so callers can auto-map arbitrary columns."""
        url = _build_sync_url(
            host=self.config.get("host"),
            port=self.config.get("port"),
            username=self.config.get("user"),
            password=self.config.get("password"),
            database=self.config.get("db"),
        )
        return SQLSchemaScanner(str(url)).scan()

    async def test_connection(self):
        if aiomysql is None:
            try:
                with self._engine.connect() as conn: conn.execute(text("SELECT 1"))
                return True
            except Exception: return False
        try:
            connection = await asyncio.wait_for(aiomysql.connect(**self.config, connect_timeout=10), timeout=12)
            connection.close()
            return True
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Timed out connecting to MySQL host {self.config.get('host')!r}:{self.config.get('port')!r}.") from exc

    def fetch_product_rows(self, table_name, columns, *, limit=200, offset=0):
        table = validate_identifier(table_name); safe_cols = [validate_identifier(c) for c in columns]
        if not safe_cols: return []
        sql = text(f"SELECT {', '.join(f'`{c}`' for c in safe_cols)} FROM `{table}` LIMIT :limit OFFSET :offset")
        with self._engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(sql, {"limit": int(limit), "offset": int(offset)})]

    def fetch_product_rows_incremental(self, table_name, columns, *, updated_column=None, created_column=None, id_column=None, watermark_at=None, watermark_id=None, limit=200, upper_bound=None):
        table = validate_identifier(table_name); safe_cols = [validate_identifier(c) for c in columns]
        if not safe_cols: return []
        ts = validate_identifier(updated_column or created_column) if (updated_column or created_column) else None
        ident = validate_identifier(id_column) if id_column else None
        params: dict[str, Any] = {"limit": int(limit)}; predicates = []
        if ts and watermark_at is not None:
            if ident and watermark_id is not None:
                predicates.append(f"(`{ts}` > :watermark_at OR (`{ts}` = :watermark_at AND `{ident}` > :watermark_id))")
                params.update(watermark_at=watermark_at, watermark_id=watermark_id)
            else:
                predicates.append(f"`{ts}` > :watermark_at"); params["watermark_at"] = watermark_at
        elif ident and watermark_id is not None:
            predicates.append(f"`{ident}` > :watermark_id"); params["watermark_id"] = watermark_id
        if upper_bound is not None and ts:
            predicates.append(f"`{ts}` <= :upper_bound"); params["upper_bound"] = upper_bound
        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        order = f" ORDER BY `{ts}` ASC, `{ident}` ASC" if ts and ident else (f" ORDER BY `{ts}` ASC" if ts else (f" ORDER BY `{ident}` ASC" if ident else ""))
        sql = text(f"SELECT {', '.join(f'`{c}`' for c in safe_cols)} FROM `{table}`{where}{order} LIMIT :limit")
        with self._engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(sql, params)]

    def get_sync_watermark(self, table_name, timestamp_column=None, id_column=None, *, upper_bound=None):
        table = validate_identifier(table_name)
        ts = validate_identifier(timestamp_column) if timestamp_column else None
        ident = validate_identifier(id_column) if id_column else None
        bound = " WHERE `{ts}` IS NOT NULL" if ts else ""
        params = {}
        if ts and upper_bound is not None:
            bound += " AND `{ts}` <= :upper_bound"
            params["upper_bound"] = upper_bound
        if ts and ident:
            sql = text(f"SELECT `{ts}` AS watermark_at, `{ident}` AS watermark_id FROM `{table}`{bound.replace('{ts}', ts)} ORDER BY `{ts}` DESC, `{ident}` DESC LIMIT 1")
        elif ts:
            sql = text(f"SELECT MAX(`{ts}`) AS watermark_at FROM `{table}`{bound.replace('{ts}', ts)}")
        elif ident:
            sql = text(f"SELECT MAX(`{ident}`) AS watermark_id FROM `{table}`")
        else:
            return {}
        with self._engine.connect() as conn:
            row = conn.execute(sql, params).first()
            return dict(row._mapping) if row else {}

    async def execute_query(self, sql, params=None):
        def run_query():
            with self._engine.connect() as conn:
                return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]
        return await asyncio.to_thread(run_query)
