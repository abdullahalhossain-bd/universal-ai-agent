"""
Sync job processor.

Job payload (canonical):
  {
    "store_id": str,
    "datasource_id": str | None,   # preferred — loads config from DB
    "connector_type": str | None,  # required if no datasource_id
    "connection_url": str | None,
    "table_name": str | None,
    "mapping": dict | None,
    "full_sync": bool = True,
    "job_type": "product_sync" | "stock_refresh",
  }

When datasource_id is provided, connection details are loaded from the
datasources table (store-scoped). Redis jobs should prefer datasource_id
so secrets are not the primary job payload source.
"""

from __future__ import annotations

import logging
from typing import Any

from app.connectors.credential_store import get_credential_store
from app.connectors.factory import ConnectorFactory
from app.db.database import SessionLocal
from app.sync.result import SyncResult
from app.sync.service import ProductSyncService

logger = logging.getLogger("app.sync.processor")


def _resolve_job(job: dict[str, Any], db) -> dict[str, Any]:
    """Merge persisted datasource config into the job when datasource_id set."""
    store_id = job.get("store_id") or job.get("tenant_id")
    datasource_id = job.get("datasource_id")

    if not datasource_id:
        return {
            "store_id": store_id,
            "datasource_id": None,
            "connector_type": job.get("connector_type"),
            "connection_url": job.get("connection_url"),
            "table_name": job.get("table_name"),
            "mapping": job.get("mapping") or {},
            "full_sync": bool(job.get("full_sync", True)),
            "job_type": job.get("job_type", "product_sync"),
        }

    from app.db.models import DataSource

    ds = (
        db.query(DataSource)
        .filter(
            DataSource.id == datasource_id,
            DataSource.store_id == store_id,
        )
        .first()
    )
    if ds is None:
        raise LookupError(
            f"datasource {datasource_id} not found for store {store_id}"
        )
    if not ds.active:
        raise PermissionError(f"datasource {datasource_id} is inactive")

    # ds.connection_url is ciphertext at rest — decrypt it here, the
    # one place a persisted datasource's connection is resolved for
    # an actual sync run.
    decrypted_url = (
        get_credential_store().decrypt(ds.connection_url)
        if ds.connection_url
        else None
    )

    return {
        "store_id": store_id,
        "datasource_id": ds.id,
        "connector_type": ds.connector_type,
        "connection_url": decrypted_url or job.get("connection_url"),
        "table_name": ds.table_name or job.get("table_name"),
        "mapping": ds.mapping or job.get("mapping") or {},
        "full_sync": bool(ds.full_sync if "full_sync" not in job else job.get("full_sync", True)),
        "job_type": job.get("job_type", "product_sync"),
    }


async def process_sync(job: dict[str, Any]) -> SyncResult:
    store_id = job.get("store_id") or job.get("tenant_id")
    if not store_id:
        result = SyncResult(store_id="")
        result.errors.append("job missing store_id")
        return result

    db = SessionLocal()
    try:
        try:
            resolved = _resolve_job(job, db)
        except LookupError as exc:
            result = SyncResult(store_id=store_id)
            result.errors.append(str(exc))
            return result
        except PermissionError as exc:
            result = SyncResult(store_id=store_id)
            result.errors.append(str(exc))
            return result

        connector_type = resolved["connector_type"]
        connection_url = resolved["connection_url"]
        table_name = resolved["table_name"]
        mapping = resolved["mapping"] or {}
        full_sync = resolved["full_sync"]
        job_type = resolved["job_type"]
        datasource_id = resolved.get("datasource_id")

        if not connector_type or not connection_url:
            result = SyncResult(store_id=store_id)
            result.errors.append(
                "job missing connector_type or connection_url"
            )
            return result

        if not table_name:
            result = SyncResult(store_id=store_id)
            result.errors.append("job missing table_name")
            return result

        if not mapping:
            result = SyncResult(store_id=store_id)
            result.errors.append("job missing field mapping")
            return result

        try:
            connector = ConnectorFactory.create(
                connector_type,
                connection_url,
            )
        except Exception as exc:
            result = SyncResult(store_id=store_id)
            result.errors.append(f"connector create failed: {exc}")
            return result

        if not hasattr(connector, "fetch_product_rows"):
            result = SyncResult(store_id=store_id)
            result.errors.append(
                f"{type(connector).__name__} does not support product row fetch"
            )
            return result

        service = ProductSyncService(db)

        if job_type == "stock_refresh":
            columns = []
            for entry in mapping.values():
                col = entry.get("column") if isinstance(entry, dict) else entry
                if col and col not in columns:
                    columns.append(col)

            rows: list[dict] = []
            offset = 0
            page_size = 200
            while True:
                page = connector.fetch_product_rows(
                    table_name,
                    columns,
                    limit=page_size,
                    offset=offset,
                )
                if not page:
                    break
                rows.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size

            result = service.refresh_stock(store_id, rows, mapping)
        else:
            result = service.sync_from_connector(
                store_id,
                connector,
                table_name,
                mapping,
                full_sync=full_sync,
            )

        # Persist status when we know the datasource
        if datasource_id:
            from app.datasources.service import DataSourceService

            status = "success" if not result.errors else "error"
            error_msg = "; ".join(result.errors) if result.errors else None
            DataSourceService(db).record_sync_result(
                store_id,
                datasource_id,
                status=status,
                error=error_msg,
            )

        logger.info(
            "sync complete store=%s created=%s updated=%s unchanged=%s "
            "stock_zeroed=%s skipped=%s errors=%s",
            store_id,
            result.created,
            result.updated,
            result.unchanged,
            result.stock_zeroed,
            result.skipped,
            len(result.errors),
        )
        return result

    except Exception as exc:
        logger.exception("process_sync failed store=%s", store_id)
        result = SyncResult(store_id=store_id)
        result.errors.append(str(exc))
        return result
    finally:
        db.close()
