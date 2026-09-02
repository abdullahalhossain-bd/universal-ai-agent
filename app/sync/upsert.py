"""
Batch upsert of normalized products into the local products table.

Identity is always (product_id, store_id). Commits in configurable batches
so a large catalog does not hold one giant transaction or commit per row.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Product
from app.sync.result import SyncResult


_TRACKED_FIELDS = (
    "name",
    "description",
    "price",
    "stock",
    "image_url",
    "product_url",
)


def _changed(existing: Product, data: dict) -> bool:
    for field in _TRACKED_FIELDS:
        if getattr(existing, field) != data.get(field):
            return True
    return False


def upsert_products(
    db: Session,
    store_id: str,
    products: list[dict],
    *,
    batch_size: int = 100,
    result: SyncResult | None = None,
) -> SyncResult:
    """
    Upsert normalized product dicts for a single store.

    Each dict must contain at least ``id`` and ``name``. Idempotent:
    re-syncing identical data yields ``unchanged``.
    """
    if result is None:
        result = SyncResult(store_id=store_id)

    if not products:
        return result

    # Preload existing rows for this batch's product ids (one query).
    ids = [p["id"] for p in products]
    existing_rows = (
        db.query(Product)
        .filter(
            Product.store_id == store_id,
            Product.id.in_(ids),
        )
        .all()
    )
    by_id: dict[str, Product] = {row.id: row for row in existing_rows}

    pending = 0
    for data in products:
        product_id = data["id"]
        existing = by_id.get(product_id)

        if existing is None:
            row = Product(
                id=product_id,
                store_id=store_id,
                name=data["name"],
                description=data.get("description"),
                price=data.get("price"),
                stock=data.get("stock"),
                image_url=data.get("image_url"),
                product_url=data.get("product_url"),
            )
            db.add(row)
            by_id[product_id] = row
            result.created += 1
            pending += 1
        elif _changed(existing, data):
            for field in _TRACKED_FIELDS:
                setattr(existing, field, data.get(field))
            result.updated += 1
            pending += 1
        else:
            result.unchanged += 1

        if pending >= batch_size:
            db.commit()
            pending = 0

    if pending:
        db.commit()

    return result


def zero_missing_stock(
    db: Session,
    store_id: str,
    seen_ids: set[str],
    *,
    batch_size: int = 200,
    result: SyncResult | None = None,
) -> SyncResult:
    """
    Safe deleted-product strategy: products present in the local catalog
    for this store but absent from the current full sync payload have
    their stock set to 0 (treated as out-of-stock) rather than being
    hard-deleted. Preserves history and avoids breaking chat references.
    """
    if result is None:
        result = SyncResult(store_id=store_id)

    q = db.query(Product).filter(Product.store_id == store_id)
    if seen_ids:
        q = q.filter(~Product.id.in_(seen_ids))

    pending = 0
    for row in q:
        if row.stock is None or float(row.stock) != 0.0:
            row.stock = 0.0
            result.stock_zeroed += 1
            pending += 1
            if pending >= batch_size:
                db.commit()
                pending = 0

    if pending:
        db.commit()

    return result
