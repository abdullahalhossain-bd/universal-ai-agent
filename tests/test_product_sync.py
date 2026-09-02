"""
Product synchronization tests (store-scoped, composite PK).

Coverage:
- create / update / idempotency
- stock refresh
- multiple stores sharing the same external product id
- mapping aliases (image/url vs image_url/product_url)
- failed connector
- partial sync (bad rows skipped)
- deleted product behavior (stock zeroed, not hard-deleted)
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.markers import requires_postgres

pytestmark = requires_postgres
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Product, Store
from app.sync.normalize import normalize_row
from app.sync.processor import process_sync
from app.sync.service import ProductSyncService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeConnector:
    """In-memory connector implementing fetch_product_rows."""

    def __init__(self, rows: list[dict[str, Any]], *, fail: bool = False):
        self._rows = rows
        self._fail = fail
        self.calls: list[tuple[int, int]] = []

    def fetch_product_rows(
        self,
        table_name: str,
        columns: list[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if self._fail:
            raise RuntimeError("connector unavailable")
        self.calls.append((limit, offset))
        page = self._rows[offset : offset + limit]
        out = []
        for row in page:
            out.append({c: row.get(c) for c in columns})
        return out


class SyncTestBase:
    @pytest.fixture(autouse=True)
    def _db(self):
        self.db: Session = SessionLocal()
        self._store_ids: list[str] = []
        yield
        try:
            if self._store_ids:
                self.db.query(Product).filter(
                    Product.store_id.in_(self._store_ids)
                ).delete(synchronize_session=False)
                self.db.query(Store).filter(
                    Store.id.in_(self._store_ids)
                ).delete(synchronize_session=False)
                self.db.commit()
        finally:
            self.db.close()

    def make_store(self, name: str | None = None) -> Store:
        store = Store(
            id=str(uuid.uuid4()),
            name=name or f"sync-store-{uuid.uuid4().hex[:8]}",
        )
        self.db.add(store)
        self.db.commit()
        self._store_ids.append(store.id)
        return store


MAPPING = {
    "id": "item_ref",
    "name": "item_title",
    "price": "sell_amt",
    "stock": "available_qty",
    "description": "details",
    "image": "pic",
    "url": "link",
}


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_mapping_aliases(self):
        raw = {
            "item_ref": "SKU-1",
            "item_title": "Widget",
            "sell_amt": "12.50",
            "available_qty": "4",
            "pic": "http://img/x.png",
            "link": "http://shop/x",
            "details": "A widget",
        }
        out = normalize_row(raw, MAPPING)
        assert out is not None
        assert out["id"] == "SKU-1"
        assert out["name"] == "Widget"
        assert out["price"] == 12.5
        assert out["stock"] == 4.0
        assert out["image_url"] == "http://img/x.png"
        assert out["product_url"] == "http://shop/x"
        assert out["description"] == "A widget"

    def test_missing_required_returns_none(self):
        assert normalize_row({"item_title": "X"}, MAPPING) is None
        assert normalize_row({"item_ref": "1"}, MAPPING) is None


# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------

class TestProductSync(SyncTestBase):
    def test_create(self):
        store = self.make_store()
        rows = [
            {
                "item_ref": "P1",
                "item_title": "Alpha",
                "sell_amt": 10,
                "available_qty": 5,
            },
            {
                "item_ref": "P2",
                "item_title": "Beta",
                "sell_amt": 20,
                "available_qty": 0,
            },
        ]
        result = ProductSyncService(self.db).sync_rows(
            store.id, rows, MAPPING, full_sync=False
        )
        assert result.created == 2
        assert result.updated == 0
        assert result.errors == []

        products = (
            self.db.query(Product)
            .filter(Product.store_id == store.id)
            .order_by(Product.id)
            .all()
        )
        assert [p.id for p in products] == ["P1", "P2"]
        assert products[0].name == "Alpha"
        assert float(products[0].price) == 10.0
        assert float(products[0].stock) == 5.0

    def test_update(self):
        store = self.make_store()
        svc = ProductSyncService(self.db)
        svc.sync_rows(
            store.id,
            [{"item_ref": "P1", "item_title": "Old", "sell_amt": 1, "available_qty": 1}],
            MAPPING,
        )
        result = svc.sync_rows(
            store.id,
            [{"item_ref": "P1", "item_title": "New", "sell_amt": 9, "available_qty": 3}],
            MAPPING,
        )
        assert result.created == 0
        assert result.updated == 1
        product = (
            self.db.query(Product)
            .filter(Product.store_id == store.id, Product.id == "P1")
            .one()
        )
        assert product.name == "New"
        assert float(product.price) == 9.0
        assert float(product.stock) == 3.0

    def test_idempotent_unchanged(self):
        store = self.make_store()
        svc = ProductSyncService(self.db)
        row = {
            "item_ref": "P1",
            "item_title": "Same",
            "sell_amt": 5,
            "available_qty": 2,
        }
        svc.sync_rows(store.id, [row], MAPPING)
        result = svc.sync_rows(store.id, [row], MAPPING)
        assert result.created == 0
        assert result.updated == 0
        assert result.unchanged == 1

    def test_stock_refresh_only(self):
        store = self.make_store()
        svc = ProductSyncService(self.db)
        svc.sync_rows(
            store.id,
            [
                {
                    "item_ref": "P1",
                    "item_title": "Keep",
                    "sell_amt": 10,
                    "available_qty": 5,
                }
            ],
            MAPPING,
        )
        result = svc.refresh_stock(
            store.id,
            [
                {
                    "item_ref": "P1",
                    "item_title": "Keep",
                    "sell_amt": 10,
                    "available_qty": 1,
                }
            ],
            MAPPING,
        )
        assert result.updated == 1
        product = (
            self.db.query(Product)
            .filter(Product.store_id == store.id, Product.id == "P1")
            .one()
        )
        assert float(product.stock) == 1.0
        assert product.name == "Keep"

    def test_stock_refresh_skips_unknown(self):
        store = self.make_store()
        svc = ProductSyncService(self.db)
        result = svc.refresh_stock(
            store.id,
            [
                {
                    "item_ref": "NOPE",
                    "item_title": "Ghost",
                    "available_qty": 9,
                }
            ],
            MAPPING,
        )
        assert result.skipped == 1
        assert result.updated == 0

    def test_multiple_stores_same_external_id(self):
        a = self.make_store("A")
        b = self.make_store("B")
        svc = ProductSyncService(self.db)
        row = {
            "item_ref": "SHARED",
            "item_title": "Shared SKU",
            "sell_amt": 1,
            "available_qty": 1,
        }
        svc.sync_rows(a.id, [row], MAPPING)
        svc.sync_rows(
            b.id,
            [
                {
                    "item_ref": "SHARED",
                    "item_title": "Shared SKU B",
                    "sell_amt": 2,
                    "available_qty": 9,
                }
            ],
            MAPPING,
        )
        pa = (
            self.db.query(Product)
            .filter(Product.store_id == a.id, Product.id == "SHARED")
            .one()
        )
        pb = (
            self.db.query(Product)
            .filter(Product.store_id == b.id, Product.id == "SHARED")
            .one()
        )
        assert pa.name == "Shared SKU"
        assert pb.name == "Shared SKU B"
        assert float(pa.price) == 1.0
        assert float(pb.price) == 2.0

    def test_partial_sync_skips_bad_rows(self):
        store = self.make_store()
        rows = [
            {"item_ref": "OK", "item_title": "Good", "sell_amt": 1},
            {"item_title": "Missing id"},  # skipped
            {"item_ref": "OK2", "item_title": "Also good", "sell_amt": 2},
        ]
        result = ProductSyncService(self.db).sync_rows(
            store.id, rows, MAPPING, full_sync=False
        )
        assert result.created == 2
        assert result.skipped == 1

    def test_deleted_product_stock_zeroed_not_hard_deleted(self):
        store = self.make_store()
        svc = ProductSyncService(self.db)
        svc.sync_rows(
            store.id,
            [
                {"item_ref": "KEEP", "item_title": "Keep", "available_qty": 3},
                {"item_ref": "GONE", "item_title": "Gone", "available_qty": 7},
            ],
            MAPPING,
            full_sync=False,
        )
        result = svc.sync_rows(
            store.id,
            [{"item_ref": "KEEP", "item_title": "Keep", "available_qty": 3}],
            MAPPING,
            full_sync=True,
        )
        assert result.stock_zeroed == 1
        gone = (
            self.db.query(Product)
            .filter(Product.store_id == store.id, Product.id == "GONE")
            .one()
        )
        assert float(gone.stock) == 0.0
        # Row still exists — not hard-deleted.
        assert gone.name == "Gone"

    def test_sync_from_connector(self):
        store = self.make_store()
        connector = _FakeConnector(
            [
                {
                    "item_ref": "C1",
                    "item_title": "From connector",
                    "sell_amt": 15,
                    "available_qty": 2,
                    "pic": None,
                    "link": None,
                    "details": None,
                }
            ]
        )
        result = ProductSyncService(self.db).sync_from_connector(
            store.id,
            connector,
            "merchant_products",
            MAPPING,
            full_sync=False,
        )
        assert result.created == 1
        assert result.errors == []

    def test_failed_connector(self):
        store = self.make_store()
        connector = _FakeConnector([], fail=True)
        with pytest.raises(RuntimeError, match="connector fetch failed"):
            ProductSyncService(self.db).sync_from_connector(
                store.id,
                connector,
                "merchant_products",
                MAPPING,
            )


# ---------------------------------------------------------------------------
# process_sync job path
# ---------------------------------------------------------------------------

class TestProcessSync(SyncTestBase):
    @pytest.mark.asyncio
    async def test_missing_fields_reported(self):
        result = await process_sync({"store_id": "x"})
        assert result.errors
        assert any("connector_type" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_unsupported_connector_type(self):
        result = await process_sync(
            {
                "store_id": str(uuid.uuid4()),
                "connector_type": "rest",
                "connection_url": "https://example.com",
                "table_name": "products",
                "mapping": MAPPING,
            }
        )
        # REST connector has no fetch_product_rows
        assert result.errors
        assert any(
            "does not support" in e or "Unsupported" in e for e in result.errors
        )
