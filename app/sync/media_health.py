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
    query=db.query(Product).filter(Product.store_id==store_id,Product.source_datasource_id==datasource_id,Product.is_active.is_(True)).order_by(Product.id)
    total=url_missing=image_missing=url_broken=image_broken=0
    checked=0
    while True:
        products=query.offset(checked).limit(batch_size).all()
        if not products: break
        now=datetime.utcnow();urls=[p.product_url for p in products if p.product_url];images=[p.image_url for p in products if p.image_url]
        url_results=await verify_product_urls(urls,concurrency=20);image_results=await verify_image_urls(images)
        for p in products:
            url_status="missing" if not p.product_url else("valid" if url_results.get(p.product_url,False) else "broken")
            image_status="missing" if not p.image_url else("valid" if image_results.get(p.image_url,False) else "broken")
            if url_status=="missing":url_missing+=1
            elif url_status=="broken":url_broken+=1
            if image_status=="missing":image_missing+=1
            elif image_status=="broken":image_broken+=1
            row=db.query(ProductMediaHealth).filter(ProductMediaHealth.store_id==store_id,ProductMediaHealth.product_id==p.id).first()
            if row is None:
                row=ProductMediaHealth(id=str(uuid.uuid4()),store_id=store_id,source_datasource_id=datasource_id,product_id=p.id);db.add(row)
            row.source_datasource_id=datasource_id;row.url_status=url_status;row.image_status=image_status;row.url_checked_at=now;row.image_checked_at=now
        total+=len(products);checked+=len(products);db.commit()
    return {"products_checked":total,"url":{"missing":url_missing,"valid":max(0,total-url_missing-url_broken),"broken":url_broken},"image":{"missing":image_missing,"valid":max(0,total-image_missing-image_broken),"broken":image_broken},"checked_at":datetime.utcnow().isoformat()}
