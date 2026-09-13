"""Verify and persist media health with fingerprint-aware caching.

Changed/new products are checked immediately. Unchanged products reuse recent
health results and are periodically revalidated, avoiding a full HTTP sweep on
every sync.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import Product
from app.sync.media_models import ProductMediaHealth
from app.sync.url_health import verify_product_urls
from app.images.url_verifier import verify_image_urls


def _recheck_after() -> timedelta:
    try:
        hours = max(1.0, float(os.getenv("MEDIA_HEALTH_RECHECK_HOURS", "24")))
    except (TypeError, ValueError):
        hours = 24.0
    return timedelta(hours=hours)


async def verify_and_persist_media_health(db: Session, *, store_id: str, datasource_id: str, batch_size: int = 500) -> dict:
    total = url_missing = image_missing = url_broken = image_broken = 0
    reused = verified = 0
    last_id = None
    cutoff = datetime.utcnow() - _recheck_after()

    while True:
        # Apply the cursor predicate before LIMIT. SQLAlchemy 2.x rejects
        # Query.filter() after LIMIT/OFFSET, which previously dead-lettered
        # every multi-batch media-health sync in production.
        q = db.query(Product).filter(
            Product.store_id == store_id,
            Product.source_datasource_id == datasource_id,
            Product.is_active.is_(True),
        )
        if last_id is not None:
            q = q.filter(Product.id > last_id)
        products = q.order_by(Product.id).limit(batch_size).all()
        if not products:
            break
        last_id = products[-1].id
        now = datetime.utcnow()
        product_ids = [p.id for p in products]
        existing = db.query(ProductMediaHealth).filter(
            ProductMediaHealth.store_id == store_id,
            ProductMediaHealth.source_datasource_id == datasource_id,
            ProductMediaHealth.product_id.in_(product_ids),
        ).all()
        by_product = {r.product_id: r for r in existing}

        fresh_by_id = {}
        to_check = []
        for p in products:
            row = by_product.get(p.id)
            fresh = bool(
                row is not None and p.source_fingerprint
                and row.source_fingerprint == p.source_fingerprint
                and row.url_checked_at is not None and row.image_checked_at is not None
                and row.url_checked_at >= cutoff and row.image_checked_at >= cutoff
            )
            fresh_by_id[p.id] = fresh
            if fresh:
                reused += 1
            else:
                to_check.append(p)

        url_results = await verify_product_urls([p.product_url for p in to_check if p.product_url], concurrency=20) if to_check else {}
        image_results = await verify_image_urls([p.image_url for p in to_check if p.image_url]) if to_check else {}
        verified += len(to_check)

        for p in products:
            row = by_product.get(p.id)
            if row is None:
                row = ProductMediaHealth(id=str(uuid.uuid4()), store_id=store_id, source_datasource_id=datasource_id, product_id=p.id)
                db.add(row)
                by_product[p.id] = row
            if not fresh_by_id[p.id]:
                row.url_status = "missing" if not p.product_url else ("valid" if url_results.get(p.product_url, False) else "broken")
                row.image_status = "missing" if not p.image_url else ("valid" if image_results.get(p.image_url, False) else "broken")
                row.url_checked_at = now
                row.image_checked_at = now
            row.source_fingerprint = p.source_fingerprint
            total += 1
            url_missing += row.url_status == "missing"
            url_broken += row.url_status == "broken"
            image_missing += row.image_status == "missing"
            image_broken += row.image_status == "broken"
        db.commit()

    return {
        "products_checked": total,
        "products_verified": verified,
        "products_reused": reused,
        "url": {"missing": url_missing, "valid": max(0, total - url_missing - url_broken), "broken": url_broken},
        "image": {"missing": image_missing, "valid": max(0, total - image_missing - image_broken), "broken": image_broken},
        "recheck_after_hours": _recheck_after().total_seconds() / 3600,
        "checked_at": datetime.utcnow().isoformat(),
    }
