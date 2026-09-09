"""Verify and persist URL/image health for every active synced product."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models import Product
from app.sync.media_models import ProductMediaHealth
from app.sync.url_health import verify_product_urls
from app.images.url_verifier import verify_image_urls

async def verify_and_persist_media_health(db: Session, *, store_id: str, datasource_id: str, batch_size: int = 500) -> dict:
    """Persist media health without OFFSET pagination or per-product queries."""
    total=url_missing=image_missing=url_broken=image_broken=0
    last_id=None
    while True:
        q=db.query(Product).filter(
            Product.store_id==store_id,
            Product.source_datasource_id==datasource_id,
            Product.is_active.is_(True),
        ).order_by(Product.id).limit(batch_size)
        if last_id is not None:
            q=q.filter(Product.id>last_id)
        products=q.all()
        if not products:
            break
        last_id=products[-1].id
        now=datetime.utcnow()
        urls=[p.product_url for p in products if p.product_url]
        images=[p.image_url for p in products if p.image_url]
        url_results=await verify_product_urls(urls,concurrency=20)
        image_results=await verify_image_urls(images)
        product_ids=[p.id for p in products]
        existing=db.query(ProductMediaHealth).filter(
            ProductMediaHealth.store_id==store_id,
            ProductMediaHealth.source_datasource_id==datasource_id,
            ProductMediaHealth.product_id.in_(product_ids),
        ).all()
        by_product={r.product_id:r for r in existing}
        for p in products:
            url_status="missing" if not p.product_url else ("valid" if url_results.get(p.product_url,False) else "broken")
            image_status="missing" if not p.image_url else ("valid" if image_results.get(p.image_url,False) else "broken")
            url_missing += url_status=="missing"; url_broken += url_status=="broken"
            image_missing += image_status=="missing"; image_broken += image_status=="broken"
            row=by_product.get(p.id)
            if row is None:
                row=ProductMediaHealth(id=str(uuid.uuid4()),store_id=store_id,source_datasource_id=datasource_id,product_id=p.id)
                db.add(row);by_product[p.id]=row
            row.url_status=url_status;row.image_status=image_status
            row.url_checked_at=now;row.image_checked_at=now
        total+=len(products)
        db.commit()
    return {
        "products_checked":total,
        "url":{"missing":url_missing,"valid":max(0,total-url_missing-url_broken),"broken":url_broken},
        "image":{"missing":image_missing,"valid":max(0,total-image_missing-image_broken),"broken":image_broken},
        "checked_at":datetime.utcnow().isoformat(),
    }
