"""Sync job processor with incremental sync, retries, history and quality controls."""
from __future__ import annotations

import inspect
import logging
import time
from datetime import datetime

from app.connectors.config import ConnectorConfig
from app.connectors.credential_store import get_credential_store
from app.connectors.factory import ConnectorFactory
from app.db.database import SessionLocal
from app.db.models import DataSource, SyncRun
from app.sync.normalize import discover_mapping
from app.sync.result import SyncResult
from app.sync.retry import run_with_retry
from app.sync.service import ProductSyncService
from app.sync.quality import repair_suggestions, schema_analysis
from app.sync.stale import apply_stale_policy

logger = logging.getLogger("app.sync.processor")


def _resolve_job(job, db):
    store_id = job.get("store_id") or job.get("tenant_id")
    datasource_id = job.get("datasource_id")
    if not datasource_id:
        return {"store_id": store_id, "datasource_id": None, "connector_type": job.get("connector_type"), "connection_url": job.get("connection_url"), "api_base_url": job.get("api_base_url"), "table_name": job.get("table_name"), "mapping": job.get("mapping") or {}, "full_sync": bool(job.get("full_sync", True)), "job_type": job.get("job_type", "product_sync")}
    ds = db.query(DataSource).filter(DataSource.id == datasource_id, DataSource.store_id == store_id).first()
    if ds is None: raise LookupError(f"datasource {datasource_id} not found for store {store_id}")
    if not ds.active: raise PermissionError(f"datasource {datasource_id} is inactive")
    decrypted = get_credential_store().decrypt(ds.connection_url) if ds.connection_url else None
    return {"store_id": store_id, "datasource_id": ds.id, "connector_type": ds.connector_type, "connection_url": decrypted or job.get("connection_url"), "api_base_url": ds.api_base_url, "table_name": ds.table_name or job.get("table_name"), "mapping": ds.mapping or job.get("mapping") or {}, "full_sync": bool(ds.full_sync if "full_sync" not in job else job.get("full_sync", True)), "job_type": job.get("job_type", "product_sync")}


def _mapping_column(mapping, field):
    entry = mapping.get(field)
    return entry.get("column") if isinstance(entry, dict) else (entry or None)


def _persist_watermark(db, datasource_id, mapping, connector, table_name, *, upper_bound=None):
    if not datasource_id or not hasattr(connector, "get_sync_watermark"): return
    ts = _mapping_column(mapping, "updated_at") or _mapping_column(mapping, "created_at")
    ident = _mapping_column(mapping, "id")
    if not ts and not ident: return
    watermark = connector.get_sync_watermark(table_name, ts, ident, upper_bound=upper_bound)
    if not watermark: return
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if ds is None: return
    state = dict((ds.mapping or {}).get("_sync_state") or {})
    state["initialized"] = True
    if watermark.get("watermark_at") is not None:
        value = watermark["watermark_at"]
        state["watermark_at"] = value.isoformat() if isinstance(value, datetime) else str(value)
    if watermark.get("watermark_id") is not None: state["watermark_id"] = str(watermark["watermark_id"])
    state["strategy"] = "updated_at+id" if _mapping_column(mapping, "updated_at") else ("created_at+id" if _mapping_column(mapping, "created_at") else "id")
    new_mapping = dict(ds.mapping or {})
    new_mapping["_sync_state"] = state
    ds.mapping = new_mapping
    db.commit()


async def _auto_discover_mapping(connector, table_name, mapping):
    effective = dict(mapping or {})
    discover = getattr(connector, "discover", None)
    if discover is None: return effective
    try:
        schema = discover()
        if inspect.isawaitable(schema): schema = await schema
    except Exception:
        if _mapping_column(effective, "id") and _mapping_column(effective, "name"): return effective
        raise
    tables = getattr(schema, "tables", None)
    if tables is None and isinstance(schema, dict): tables = schema.get("tables", [])
    target = None
    for table in tables or []:
        name = getattr(table, "name", None) if not isinstance(table, dict) else table.get("name")
        if str(name) == str(table_name): target = table; break
    if target is None: return effective
    columns = getattr(target, "columns", None) if not isinstance(target, dict) else target.get("columns", [])
    names = []
    for column in columns or []:
        name = getattr(column, "name", None) if not isinstance(column, dict) else column.get("name")
        if name: names.append(str(name))
    if not names: return effective
    inferred = discover_mapping({name: None for name in names}, effective)
    for field, column in inferred.items():
        if not field.startswith("_") and column and not effective.get(field): effective[field] = column
    effective["_schema_discovery"] = {"table": str(table_name), "columns": names}
    return effective


def _start_run(db, store_id, datasource_id, sync_mode):
    run = SyncRun(store_id=store_id, datasource_id=datasource_id, status="running", sync_mode=sync_mode, started_at=datetime.utcnow())
    db.add(run); db.commit(); return run


def _finish_run(db, run, result: SyncResult | None, status: str, error: str | None, started: float):
    run.status = status; run.finished_at = datetime.utcnow(); run.duration_ms = max(0, int((time.monotonic() - started) * 1000))
    if result is not None:
        run.products_seen = int(result.data_quality_report().get("products", 0)); run.created = result.created; run.updated = result.updated; run.unchanged = result.unchanged; run.skipped = result.skipped; run.stock_zeroed = result.stock_zeroed; run.health_score = result.calculate_health_score(); run.quality_report = result.data_quality_report(); run.reconciliation = result.reconciliation or {}
    run.error = error; db.commit()


async def _process_once(job):
    store_id = job.get("store_id") or job.get("tenant_id")
    if not store_id:
        result = SyncResult(store_id=""); result.errors.append("job missing store_id"); return result
    db = SessionLocal(); started = time.monotonic(); run = None; result = None
    try:
        resolved = _resolve_job(job, db); mapping = resolved["mapping"] or {}; state = mapping.get("_sync_state") or {}; datasource_id = resolved.get("datasource_id"); connector_type = resolved["connector_type"]; table_name = resolved["table_name"]
        if not connector_type: raise ValueError("job missing connector_type")
        if not table_name: raise ValueError("job missing table_name")
        if connector_type == "rest":
            base = resolved.get("api_base_url") or resolved.get("connection_url")
            if not base: raise ValueError("job missing api_base_url")
            connector = ConnectorFactory.create(ConnectorConfig(connector_type="rest", api_base_url=base, options=(mapping.get("_rest_options") or {})))
        else:
            if not resolved.get("connection_url"): raise ValueError("job missing connection_url")
            connector = ConnectorFactory.create(connector_type, resolved["connection_url"])
        previous_mapping = dict(mapping)
        mapping = await _auto_discover_mapping(connector, table_name, mapping)
        if datasource_id and mapping != resolved["mapping"]:
            ds = db.query(DataSource).filter(DataSource.id == datasource_id, DataSource.store_id == store_id).first()
            if ds is not None: ds.mapping = mapping; db.commit()
        state = mapping.get("_sync_state") or {}
        can_incremental = hasattr(connector, "fetch_product_rows_incremental") and bool(getattr(connector, "supports_incremental_sync", True))
        incremental = bool(state.get("initialized")) and bool(_mapping_column(mapping, "updated_at") or _mapping_column(mapping, "created_at") or _mapping_column(mapping, "id")) and can_incremental
        run = _start_run(db, store_id, datasource_id, "incremental" if incremental else "full")
        service = ProductSyncService(db)
        if resolved["job_type"] == "stock_refresh":
            columns = [(e.get("column") if isinstance(e, dict) else e) for f, e in mapping.items() if f not in {"_sync_state", "_schema_discovery", "_rest_options"} and (e.get("column") if isinstance(e, dict) else e)]
            rows, offset = [], 0
            while True:
                page = connector.fetch_product_rows(table_name, columns, limit=200, offset=offset)
                if not page: break
                rows.extend(page)
                if len(page) < 200: break
                offset += 200
            result = service.refresh_stock(store_id, rows, mapping)
        else:
            upper = datetime.utcnow() if incremental and (_mapping_column(mapping, "updated_at") or _mapping_column(mapping, "created_at")) else None
            result = service.sync_from_connector(store_id, connector, table_name, mapping, full_sync=resolved["full_sync"], sync_state=state, sync_upper_bound=upper, source_datasource_id=datasource_id)
            if not result.errors and datasource_id:
                _persist_watermark(db, datasource_id, mapping, connector, table_name, upper_bound=upper)
            if not result.errors and datasource_id and not incremental and resolved["full_sync"]:
                result.stale = apply_stale_policy(db, store_id=store_id, datasource_id=datasource_id, seen_ids=set(result.data_quality.get("seen_ids", [])), grace_syncs=2)
        # Schema drift is reported, never silently applied when confidence is uncertain.
        if datasource_id:
            columns = mapping.get("_schema_discovery", {}).get("columns", [])
            if columns:
                result.schema_drift = schema_analysis({c: None for c in columns}, previous_mapping).get("changes", [])
                result.repair_suggestions = repair_suggestions({"current": schema_analysis({c: None for c in columns}, previous_mapping).get("current", {})}, result.data_quality_report())
            from app.datasources.service import DataSourceService
            DataSourceService(db).record_sync_result(store_id, datasource_id, status="success" if not result.errors else "error", error="; ".join(result.errors) if result.errors else None)
        _finish_run(db, run, result, "success" if not result.errors else "partial", "; ".join(result.errors) if result.errors else None, started)
        if result.created or result.updated:
            from app.search.store_vocabulary import invalidate_store_vocabulary
            await invalidate_store_vocabulary(store_id)
        return result
    except Exception as exc:
        if db.is_active and run is not None:
            db.rollback()
            try: _finish_run(db, run, result, "error", str(exc), started)
            except Exception: db.rollback()
        logger.exception("process_sync failed store=%s", store_id)
        if result is None: result = SyncResult(store_id=store_id)
        result.errors.append(str(exc)); raise
    finally: db.close()


async def process_sync(job):
    """Run a sync with bounded retries for transient connector/database failures."""
    try:
        return await run_with_retry(lambda: _process_once(job), attempts=4, base_delay=1.0, max_delay=15.0, logger=logger)
    except Exception as exc:
        store_id = job.get("store_id") or job.get("tenant_id") or ""
        result = SyncResult(store_id=store_id); result.errors.append(str(exc)); return result
