"""Batch upsert of normalized products into the local products table."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Product
from app.sync.result import SyncResult

_TRACKED_FIELDS = (
    "name", "description", "category", "price", "currency", "stock", "image_url",
    "product_url", "source_datasource_id", "attributes",
)


def _changed(existing, data):
    for field in _TRACKED_FIELDS:
        incoming = data.get(field)
        if field == "attributes":
            incoming = incoming or {}
            current = getattr(existing, field, {}) or {}
            if current != incoming:
                return True
        elif getattr(existing, field, None) != incoming:
            return True
    return False


def _persist_attributes(db: Session, store_id: str, product_id: str, attributes: dict) -> None:
    """Persist JSON through SQL so older ORM deployments remain compatible."""
    db.execute(
        text(
            "UPDATE products SET attributes = :attributes "
            "WHERE product_id = :product_id AND store_id = :store_id"
        ),
        {
            "attributes": json.dumps(attributes or {}, ensure_ascii=False),
            "product_id": product_id,
            "store_id": store_id,
        },
    )


def upsert_products(db: Session, store_id, products, *, batch_size=100, result=None, source_datasource_id=None):
    if result is None:
        result = SyncResult(store_id=store_id)
    if not products:
        return result

    ids = [p["id"] for p in products]
    existing_rows = db.query(Product).filter(Product.store_id == store_id, Product.id.in_(ids)).all()
    by_id = {r.id: r for r in existing_rows}
    pending = 0

    for data in products:
        pid = data["id"]
        existing = by_id.get(pid)
        data = dict(data)
        if source_datasource_id:
            data["source_datasource_id"] = source_datasource_id
        data["attributes"] = data.get("attributes") or {}

        if existing is None:
            row = Product(
                id=pid,
                store_id=store_id,
                name=data["name"],
                description=data.get("description"),
                category=data.get("category"),
                price=data.get("price"),
                currency=data.get("currency"),
                stock=data.get("stock"),
                image_url=data.get("image_url"),
                product_url=data.get("product_url"),
                source_datasource_id=data.get("source_datasource_id"),
            )
            db.add(row)
            db.flush()
            _persist_attributes(db, store_id, pid, data["attributes"])
            by_id[pid] = row
            result.created += 1
            pending += 1
        elif _changed(existing, data):
            for field in _TRACKED_FIELDS:
                if field == "attributes":
                    continue
                if field in data:
                    setattr(existing, field, data.get(field))
            _persist_attributes(db, store_id, pid, data["attributes"])
            existing.attributes = data["attributes"]
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


def zero_missing_stock(db: Session, store_id, seen_ids, *, batch_size=200, result=None, source_datasource_id=None):
    if result is None:
        result = SyncResult(store_id=store_id)
    q = db.query(Product).filter(Product.store_id == store_id)
    if source_datasource_id:
        q = q.filter(Product.source_datasource_id == source_datasource_id)
    else:
        q = q.filter(Product.source_datasource_id.is_(None))
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
