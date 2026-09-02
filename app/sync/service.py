"""
Canonical product synchronization service.

Flow:
  merchant rows (via connector or in-memory)
  → normalize (field mapping)
  → batch upsert into products (store-scoped composite PK)
  → optional stock-zero for products missing from a full sync

store_id is the sole tenant boundary. Product identity is (product_id, store_id).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.db.models import Product
from app.sync.normalize import normalize_row
from app.sync.result import SyncResult
from app.sync.upsert import upsert_products, zero_missing_stock

logger = logging.getLogger("app.sync")


class ProductSyncService:
    """
    Store-scoped product sync against the local Product ORM / products table.
    """

    def __init__(
        self,
        db: Session,
        *,
        batch_size: int = 100,
    ):
        self.db = db
        self.batch_size = batch_size

    def sync_rows(
        self,
        store_id: str,
        raw_rows: Iterable[dict],
        mapping: dict,
        *,
        full_sync: bool = False,
    ) -> SyncResult:
        """
        Normalize and upsert raw merchant rows.

        Parameters
        ----------
        store_id:
            Local store boundary.
        raw_rows:
            Iterable of dict rows from the merchant database.
        mapping:
            Semantic field → column name (or {column: ...}) mapping.
        full_sync:
            When True, products in the local catalog that were not seen
            in this payload have stock set to 0 (soft deletion strategy).
        """
        result = SyncResult(store_id=store_id)
        seen: set[str] = set()
        batch: list[dict] = []

        try:
            for raw in raw_rows:
                try:
                    normalized = normalize_row(raw, mapping)
                except Exception as exc:  # noqa: BLE001 — isolate bad rows
                    result.skipped += 1
                    result.errors.append(f"normalize failed: {exc}")
                    continue

                if normalized is None:
                    result.skipped += 1
                    continue

                seen.add(normalized["id"])
                batch.append(normalized)

                if len(batch) >= self.batch_size:
                    upsert_products(
                        self.db,
                        store_id,
                        batch,
                        batch_size=self.batch_size,
                        result=result,
                    )
                    batch = []

            if batch:
                upsert_products(
                    self.db,
                    store_id,
                    batch,
                    batch_size=self.batch_size,
                    result=result,
                )

            if full_sync:
                zero_missing_stock(
                    self.db,
                    store_id,
                    seen,
                    batch_size=self.batch_size,
                    result=result,
                )

        except Exception as exc:
            self.db.rollback()
            logger.exception("product sync failed for store %s", store_id)
            result.errors.append(str(exc))
            raise

        return result

    def sync_from_connector(
        self,
        store_id: str,
        connector: Any,
        table_name: str,
        mapping: dict,
        *,
        full_sync: bool = True,
        page_size: int = 200,
    ) -> SyncResult:
        """
        Fetch all product rows from a SQL connector and upsert them.

        Requires ``connector.fetch_product_rows(table, columns, limit, offset)``.
        """
        columns = _mapping_columns(mapping)

        if not _resolve_required(mapping, "id") or not _resolve_required(
            mapping, "name"
        ):
            result = SyncResult(store_id=store_id)
            result.errors.append(
                "mapping must include semantic fields 'id' and 'name'"
            )
            return result

        def _iter_pages():
            offset = 0
            while True:
                try:
                    rows = _fetch_page(
                        connector,
                        table_name,
                        columns,
                        limit=page_size,
                        offset=offset,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"connector fetch failed at offset={offset}: {exc}"
                    ) from exc
                if not rows:
                    break
                for row in rows:
                    yield row
                if len(rows) < page_size:
                    break
                offset += page_size

        return self.sync_rows(
            store_id,
            _iter_pages(),
            mapping,
            full_sync=full_sync,
        )

    def refresh_stock(
        self,
        store_id: str,
        stock_rows: Iterable[dict],
        mapping: dict,
    ) -> SyncResult:
        """
        Lightweight stock-only refresh. Updates quantity for known products;
        does not create new products or zero missing ones.
        """
        result = SyncResult(store_id=store_id)
        batch: list[dict] = []

        for raw in stock_rows:
            normalized = normalize_row(raw, mapping)
            if normalized is None:
                result.skipped += 1
                continue
            batch.append(normalized)
            if len(batch) >= self.batch_size:
                self._stock_only_upsert(store_id, batch, result)
                batch = []

        if batch:
            self._stock_only_upsert(store_id, batch, result)

        return result

    def _stock_only_upsert(
        self,
        store_id: str,
        products: list[dict],
        result: SyncResult,
    ) -> None:
        ids = [p["id"] for p in products]
        existing = (
            self.db.query(Product)
            .filter(
                Product.store_id == store_id,
                Product.id.in_(ids),
            )
            .all()
        )
        by_id = {row.id: row for row in existing}
        pending = 0
        for data in products:
            row = by_id.get(data["id"])
            if row is None:
                result.skipped += 1
                continue
            new_stock = data.get("stock")
            if row.stock != new_stock:
                row.stock = new_stock
                result.updated += 1
                pending += 1
            else:
                result.unchanged += 1
        if pending:
            self.db.commit()


def _resolve_required(mapping: dict, field: str) -> bool:
    entry = mapping.get(field)
    if entry is None:
        return False
    if isinstance(entry, dict):
        return bool(entry.get("column"))
    return bool(entry)


def _mapping_columns(mapping: dict) -> list[str]:
    cols: list[str] = []
    seen: set[str] = set()
    for entry in mapping.values():
        if isinstance(entry, dict):
            col = entry.get("column")
        else:
            col = entry
        if col and col not in seen:
            seen.add(col)
            cols.append(col)
    return cols


def _fetch_page(
    connector: Any,
    table_name: str,
    columns: list[str],
    *,
    limit: int,
    offset: int,
) -> list[dict]:
    if hasattr(connector, "fetch_product_rows"):
        return connector.fetch_product_rows(
            table_name,
            columns,
            limit=limit,
            offset=offset,
        )
    raise TypeError(
        f"connector {type(connector).__name__} does not implement "
        "fetch_product_rows(table, columns, limit, offset)"
    )
