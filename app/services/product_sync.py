"""
Legacy thin wrapper around the canonical ProductSyncService.

Kept so any residual imports keep working. Prefer
``app.sync.service.ProductSyncService`` for new code.

Only maps fields that exist on the products table:
  product_id, store_id, product_name, description, selling_price,
  quantity, main_image, product_url
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.sync.service import ProductSyncService


def sync_product(
    db: Session,
    store_id: str,
    raw_product: dict,
    mapping: dict,
):
    service = ProductSyncService(db, batch_size=1)
    return service.sync_rows(
        store_id,
        [raw_product],
        mapping,
        full_sync=False,
    )


def sync_products(
    db: Session,
    store_id: str,
    raw_products: list[dict],
    mapping: dict,
    *,
    full_sync: bool = False,
):
    service = ProductSyncService(db)
    result = service.sync_rows(
        store_id,
        raw_products,
        mapping,
        full_sync=full_sync,
    )
    return result.created + result.updated + result.unchanged
