"""
DataSource CRUD + discover/test helpers.

store_id is enforced on every query.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.credential_store import get_credential_store
from app.connectors.factory import ConnectorFactory
from app.connectors.mapping_engine import MappingEngine
from app.core.network_guard import assert_safe_connection_host
from app.db.models import DataSource, Store
from app.discovery.scanners.sql_scanner import SQLSchemaScanner
from app.discovery.table_detector import detect_table

logger = logging.getLogger("app.datasources")

SUPPORTED_SYNC_TYPES = {"postgresql", "mysql", "postgres"}
AUTO_MAP_THRESHOLD = 0.85


class DataSourceService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Queries (always store-scoped)
    # ------------------------------------------------------------------

    def get(self, store_id: str, datasource_id: str) -> DataSource | None:
        return (
            self.db.query(DataSource)
            .filter(
                DataSource.store_id == store_id,
                DataSource.id == datasource_id,
            )
            .first()
        )

    def list_for_store(self, store_id: str) -> list[DataSource]:
        return (
            self.db.query(DataSource)
            .filter(DataSource.store_id == store_id)
            .order_by(DataSource.created_at.desc())
            .all()
        )

    def list_active(self) -> list[DataSource]:
        """All active datasources across stores (scheduler use)."""
        return (
            self.db.query(DataSource)
            .filter(DataSource.active.is_(True))
            .all()
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create(
        self,
        store_id: str,
        *,
        name: str,
        connector_type: str,
        connection_url: str | None = None,
        api_base_url: str | None = None,
        table_name: str | None = None,
        mapping: dict | None = None,
        active: bool = True,
        full_sync: bool = True,
        validate_connection: bool = True,
    ) -> DataSource:
        store = (
            self.db.query(Store).filter(Store.id == store_id).first()
        )
        if store is None:
            raise ValueError("store not found")

        ctype = connector_type.lower().strip()
        if ctype == "postgres":
            ctype = "postgresql"

        if ctype not in {"postgresql", "mysql", "rest"}:
            raise ValueError(f"unsupported connector_type: {connector_type}")

        if ctype in SUPPORTED_SYNC_TYPES and not connection_url:
            raise ValueError("connection_url required for SQL connectors")

        if ctype == "rest" and not api_base_url:
            raise ValueError("api_base_url required for REST connectors")

        if validate_connection and ctype in SUPPORTED_SYNC_TYPES:
            ok = self._test_connection_sync(ctype, connection_url)
            if not ok:
                raise ConnectionError("connection test failed")

        ds = DataSource(
            id=str(uuid.uuid4()),
            store_id=store_id,
            name=name or "default",
            connector_type=ctype,
            # Encrypted at rest — the connection test above already ran
            # against the plaintext value; only ciphertext is written
            # to the DB from here on.
            connection_url=get_credential_store().encrypt(connection_url),
            api_base_url=api_base_url,
            table_name=table_name,
            mapping=mapping,
            active=active,
            full_sync=full_sync,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(ds)
        self.db.commit()
        self.db.refresh(ds)
        return ds

    def update(
        self,
        store_id: str,
        datasource_id: str,
        **fields: Any,
    ) -> DataSource:
        ds = self.get(store_id, datasource_id)
        if ds is None:
            raise LookupError("datasource not found")

        allowed = {
            "name",
            "connection_url",
            "api_base_url",
            "table_name",
            "mapping",
            "active",
            "full_sync",
            "credential_ref",
        }
        # Re-validate connection if URL changed (against the plaintext
        # value the caller supplied, before it gets encrypted below).
        if "connection_url" in fields and fields["connection_url"]:
            if ds.connector_type in SUPPORTED_SYNC_TYPES:
                ok = self._test_connection_sync(
                    ds.connector_type, fields["connection_url"]
                )
                if not ok:
                    raise ConnectionError("connection test failed")

        for key, value in fields.items():
            if key not in allowed:
                continue
            if value is None and key in ("name",):
                continue
            if key == "connection_url" and value is not None:
                value = get_credential_store().encrypt(value)
            setattr(ds, key, value)

        ds.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ds)
        return ds

    def delete(self, store_id: str, datasource_id: str) -> bool:
        ds = self.get(store_id, datasource_id)
        if ds is None:
            return False
        self.db.delete(ds)
        self.db.commit()
        return True

    def record_sync_result(
        self,
        store_id: str,
        datasource_id: str,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        ds = self.get(store_id, datasource_id)
        if ds is None:
            return
        ds.last_sync_at = datetime.utcnow()
        ds.last_sync_status = status
        ds.last_sync_error = error
        ds.updated_at = datetime.utcnow()
        self.db.commit()

    # ------------------------------------------------------------------
    # Connection / discovery
    # ------------------------------------------------------------------

    def test_connection(
        self,
        connector_type: str,
        connection_url: str | None = None,
        api_base_url: str | None = None,
    ) -> bool:
        ctype = connector_type.lower().strip()
        if ctype == "postgres":
            ctype = "postgresql"
        return self._test_connection_sync(
            ctype, connection_url, api_base_url=api_base_url
        )

    def _test_connection_sync(
        self,
        connector_type: str,
        connection_url: str | None,
        api_base_url: str | None = None,
    ) -> bool:
        import asyncio

        try:
            if connector_type in SUPPORTED_SYNC_TYPES:
                if not connection_url:
                    return False
                # SSRF guard: a merchant-supplied connection_url must
                # never let this server reach a private/internal/
                # metadata address. Checked here (the single choke
                # point for create/update/test) and again in
                # discover() below, which has its own direct callers.
                assert_safe_connection_host(connection_url)
                connector = ConnectorFactory.create(
                    connector_type, connection_url
                )
            elif connector_type == "rest":
                from app.connectors.config import ConnectorConfig

                if api_base_url:
                    assert_safe_connection_host(api_base_url)

                connector = ConnectorFactory.create(
                    ConnectorConfig(
                        connector_type="rest",
                        api_base_url=api_base_url or "",
                    )
                )
            else:
                return False

            coro = connector.test_connection()
            if asyncio.iscoroutine(coro):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    # Running inside an existing event loop — use a thread.
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=1
                    ) as pool:
                        return pool.submit(asyncio.run, coro).result(
                            timeout=15
                        )
                return asyncio.run(coro)
            return bool(coro)
            return bool(coro)
        except Exception:
            logger.exception("connection test failed")
            return False
    def discover(
        self,
        connection_url: str,
        *,
        auto_threshold: float = AUTO_MAP_THRESHOLD,
    ) -> dict:
        """
        Scan schema, score product tables, propose field mappings.

        Does NOT persist anything. Low-confidence mappings are returned
        under needs_confirmation rather than as resolved.
        """
        # SSRF guard — see note in _test_connection_sync. discover()
        # is reachable directly (e.g. from a previously-stored
        # datasource) without going through test_connection first.
        assert_safe_connection_host(connection_url)

        scanner = SQLSchemaScanner(connection_url)
        schema = scanner.scan()

        engine = MappingEngine()
        tables_out = []

        for table in schema.tables:
            col_names = [c.name for c in table.columns]
            col_dicts = [
                {"name": c.name, "type": c.data_type} for c in table.columns
            ]
            score = detect_table(table.name, col_dicts)
            suggestions = engine.suggest(col_names)
            resolved: dict[str, str] = {}
            needs_confirmation: dict[str, list] = {}

            for candidate in suggestions:
                if candidate.confidence >= auto_threshold:
                    # Avoid double-assigning the same column to two fields.
                    if candidate.column in resolved.values():
                        needs_confirmation.setdefault(
                            candidate.field,
                            [],
                        ).append(
                            {
                                "column": candidate.column,
                                "confidence": candidate.confidence,
                            }
                        )
                    else:
                        resolved[candidate.field] = candidate.column
                else:
                    needs_confirmation.setdefault(candidate.field, []).append(
                        {
                            "column": candidate.column,
                            "confidence": candidate.confidence,
                        }
                    )

            tables_out.append(
                {
                    "table": table.name,
                    "score": score,
                    "columns": col_names,
                    "proposed_mapping": resolved,
                    "needs_confirmation": needs_confirmation,
                }
            )

        tables_out.sort(key=lambda t: t["score"], reverse=True)
        best = tables_out[0] if tables_out else None

        return {
            "tables": tables_out,
            "recommended_table": best["table"] if best else None,
            "recommended_mapping": (
                best["proposed_mapping"] if best else {}
            ),
            "needs_confirmation": (
                best["needs_confirmation"] if best else {}
            ),
        }

    @staticmethod
    def decrypt_connection_url(ds: DataSource) -> str | None:
        """
        Plaintext connection_url for a loaded DataSource, for the
        handful of call sites that need to actually open a connection
        (schema discovery, sync). Never assign the result back onto
        `ds` — the ORM object must keep holding ciphertext, or a later
        `db.commit()` on that session would write the plaintext back.
        """
        return get_credential_store().decrypt(ds.connection_url)

    def build_sync_job(self, ds: DataSource) -> dict:
        """
        Canonical job payload for process_sync / scheduler.

        Includes connection details loaded from DB so Redis jobs from the
        scheduler do not need a separate secret channel. API-triggered
        sync also uses this shape. The URL is decrypted here so it never
        needs to be stored in Redis in encrypted form.
        """
        return {
            "store_id": ds.store_id,
            "datasource_id": ds.id,
            "connector_type": ds.connector_type,
            "connection_url": self.decrypt_connection_url(ds),
            "table_name": ds.table_name,
            "mapping": ds.mapping or {},
            "full_sync": bool(ds.full_sync),
            "job_type": "product_sync",
        }

