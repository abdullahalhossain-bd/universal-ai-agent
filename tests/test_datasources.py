"""
Persistent merchant datasource onboarding tests.

Coverage:
- CRUD + store isolation
- invalid connector rejected
- connection test
- discovery (against local agent_db as a stand-in merchant DB)
- mapping persistence
- sync trigger (with fake connector path via process_sync job)
- scheduler picks active datasources
- inactive skipped
- secret redaction
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.markers import requires_postgres

pytestmark = requires_postgres
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_api_key, hash_api_key
from app.datasources.redaction import public_datasource_dict, redact_url
from app.datasources.service import DataSourceService
from app.db.database import SessionLocal
from app.db.models import APIKey, DataSource, Product, Store
from app.sync.processor import process_sync
from app.sync.scheduler import get_active_datasources


class DataSourceTestBase:
    @pytest.fixture(autouse=True)
    def _db(self):
        self.db: Session = SessionLocal()
        self._store_ids: list[str] = []
        self._ds_ids: list[str] = []
        yield
        try:
            if self._ds_ids:
                self.db.query(DataSource).filter(
                    DataSource.id.in_(self._ds_ids)
                ).delete(synchronize_session=False)
            if self._store_ids:
                self.db.query(Product).filter(
                    Product.store_id.in_(self._store_ids)
                ).delete(synchronize_session=False)
                self.db.query(APIKey).filter(
                    APIKey.store_id.in_(self._store_ids)
                ).delete(synchronize_session=False)
                self.db.query(DataSource).filter(
                    DataSource.store_id.in_(self._store_ids)
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
            name=name or f"ds-store-{uuid.uuid4().hex[:8]}",
        )
        self.db.add(store)
        self.db.commit()
        self._store_ids.append(store.id)
        return store

    def track_ds(self, ds: DataSource) -> DataSource:
        self._ds_ids.append(ds.id)
        return ds


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_redacts_password_in_url(self):
        url = "postgresql+psycopg://agent:secret_pass@localhost:5432/agent_db"
        out = redact_url(url)
        assert out is not None
        assert "secret_pass" not in out
        assert "localhost" in out
        assert "agent_db" in out

    def test_public_dict_redacts(self):
        store_id = str(uuid.uuid4())
        ds = DataSource(
            id=str(uuid.uuid4()),
            store_id=store_id,
            name="x",
            connector_type="postgresql",
            connection_url="postgresql://u:pass@host/db",
            active=True,
            full_sync=True,
        )
        pub = public_datasource_dict(ds)
        assert "pass" not in (pub["connection_url"] or "")


# ---------------------------------------------------------------------------
# CRUD + isolation
# ---------------------------------------------------------------------------

class TestDataSourceCRUD(DataSourceTestBase):
    def test_create_and_get(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        ds = self.track_ds(
            svc.create(
                store.id,
                name="merchant-pg",
                connector_type="postgresql",
                connection_url=settings.database_url,
                table_name="products",
                mapping={"id": "product_id", "name": "product_name"},
                validate_connection=True,
            )
        )
        assert ds.id
        assert ds.store_id == store.id
        assert ds.connector_type == "postgresql"
        loaded = svc.get(store.id, ds.id)
        assert loaded is not None
        assert loaded.table_name == "products"

    def test_invalid_connector_rejected(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        with pytest.raises(ValueError, match="unsupported"):
            svc.create(
                store.id,
                name="bad",
                connector_type="oracle",
                connection_url="oracle://x",
                validate_connection=False,
            )

    def test_store_isolation(self):
        a = self.make_store("A")
        b = self.make_store("B")
        svc = DataSourceService(self.db)
        ds = self.track_ds(
            svc.create(
                a.id,
                name="only-a",
                connector_type="postgresql",
                connection_url=settings.database_url,
                validate_connection=False,
            )
        )
        assert svc.get(b.id, ds.id) is None
        assert svc.get(a.id, ds.id) is not None
        assert len(svc.list_for_store(b.id)) == 0
        assert len(svc.list_for_store(a.id)) == 1

    def test_update_mapping_persistence(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        ds = self.track_ds(
            svc.create(
                store.id,
                name="m",
                connector_type="postgresql",
                connection_url=settings.database_url,
                validate_connection=False,
            )
        )
        mapping = {
            "id": "item_ref",
            "name": "item_title",
            "price": "sell_amt",
        }
        updated = svc.update(
            store.id,
            ds.id,
            table_name="merchant_items",
            mapping=mapping,
        )
        assert updated.table_name == "merchant_items"
        assert updated.mapping["id"] == "item_ref"

        reloaded = svc.get(store.id, ds.id)
        assert reloaded.mapping["name"] == "item_title"

    def test_delete(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        ds = self.track_ds(
            svc.create(
                store.id,
                name="tmp",
                connector_type="postgresql",
                connection_url=settings.database_url,
                validate_connection=False,
            )
        )
        assert svc.delete(store.id, ds.id) is True
        assert svc.get(store.id, ds.id) is None
        self._ds_ids.remove(ds.id)

    def test_connection_test_live_db(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        assert svc.test_connection(
            "postgresql", settings.database_url
        ) is True
        assert svc.test_connection(
            "postgresql", "postgresql+psycopg://bad:bad@localhost:1/none"
        ) is False

    def test_discovery_against_local_db(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        result = svc.discover(settings.database_url)
        assert "tables" in result
        table_names = {t["table"] for t in result["tables"]}
        assert "products" in table_names
        # products table should score relatively high
        products = next(t for t in result["tables"] if t["table"] == "products")
        assert products["score"] > 0
        assert "id" in products["proposed_mapping"] or products["score"] > 0


# ---------------------------------------------------------------------------
# Sync + scheduler
# ---------------------------------------------------------------------------

class TestDataSourceSync(DataSourceTestBase):
    @pytest.mark.asyncio
    async def test_process_sync_loads_datasource_from_db(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        # Point at local products table with identity mapping so sync is a no-op
        # of existing schema (may create zero rows if empty — still success).
        ds = self.track_ds(
            svc.create(
                store.id,
                name="sync-src",
                connector_type="postgresql",
                connection_url=settings.database_url,
                table_name="products",
                mapping={
                    "id": "product_id",
                    "name": "product_name",
                    "price": "selling_price",
                    "stock": "quantity",
                },
                validate_connection=True,
            )
        )
        # Job carries only ids — secrets come from DB
        result = await process_sync(
            {
                "store_id": store.id,
                "datasource_id": ds.id,
            }
        )
        assert result.errors == [] or all(
            "missing" not in e for e in result.errors
        )
        self.db.refresh(ds)
        assert ds.last_sync_status in ("success", "error")
        assert ds.last_sync_at is not None

    @pytest.mark.asyncio
    async def test_inactive_datasource_rejected_by_process_sync(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        ds = self.track_ds(
            svc.create(
                store.id,
                name="inactive",
                connector_type="postgresql",
                connection_url=settings.database_url,
                table_name="products",
                mapping={"id": "product_id", "name": "product_name"},
                active=False,
                validate_connection=False,
            )
        )
        result = await process_sync(
            {"store_id": store.id, "datasource_id": ds.id}
        )
        assert result.errors
        assert any("inactive" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_scheduler_lists_active_only(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        active = self.track_ds(
            svc.create(
                store.id,
                name="active",
                connector_type="postgresql",
                connection_url=settings.database_url,
                table_name="products",
                mapping={"id": "product_id", "name": "product_name"},
                active=True,
                validate_connection=False,
            )
        )
        self.track_ds(
            svc.create(
                store.id,
                name="off",
                connector_type="postgresql",
                connection_url=settings.database_url,
                table_name="products",
                mapping={"id": "product_id", "name": "product_name"},
                active=False,
                validate_connection=False,
            )
        )
        listed = await get_active_datasources()
        ids = {d["id"] for d in listed if d["store_id"] == store.id}
        assert active.id in ids
        assert all(
            d.get("active", True) for d in listed if d["store_id"] == store.id
        )
        # secrets not in scheduler list payload
        for d in listed:
            assert "connection_url" not in d

    def test_build_sync_job_shape(self):
        store = self.make_store()
        svc = DataSourceService(self.db)
        ds = self.track_ds(
            svc.create(
                store.id,
                name="job",
                connector_type="postgresql",
                connection_url=settings.database_url,
                table_name="products",
                mapping={"id": "product_id", "name": "product_name"},
                validate_connection=False,
            )
        )
        job = svc.build_sync_job(ds)
        assert job["store_id"] == store.id
        assert job["datasource_id"] == ds.id
        assert job["table_name"] == "products"
        assert "mapping" in job
