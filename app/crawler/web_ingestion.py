from __future__ import annotations

import hashlib
from datetime import datetime
from urllib.parse import urljoin

from app.crawler.classifier import classify_page
from app.crawler.limits import get_crawl_limits
from app.knowledge.chunk import KnowledgeChunk, KnowledgePage
from app.knowledge.chunker import TextChunker
from app.knowledge.crawler import WebsiteCrawler
from app.sync.service import ProductSyncService


def _canonical_url(url: str, base: str) -> str:
    return urljoin(base, url).split("#", 1)[0]


def _product_id(url: str, fallback: str | None = None) -> str:
    value = (url or fallback or "").strip()
    return "web_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:96]


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _offer(product: dict) -> dict:
    offers = _first(product.get("offers"))
    return offers if isinstance(offers, dict) else {}


def _image(product: dict):
    image = product.get("image")
    if isinstance(image, dict):
        return image.get("url") or image.get("contentUrl")
    if isinstance(image, list):
        return _image({"image": image[0]}) if image else None
    return image


def extract_products_from_structured_data(structured: list[dict], page_url: str) -> list[dict]:
    rows = []
    for item in structured:
        if not isinstance(item, dict):
            continue
        typ = item.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if not any(str(t).casefold() == "product" for t in types):
            continue
        offers = _offer(item)
        url = _canonical_url(item.get("url") or page_url, page_url)
        rows.append({
            "id": _product_id(url, item.get("sku") or item.get("mpn") or item.get("name")),
            "sku": item.get("sku") or item.get("mpn"),
            "name": item.get("name"),
            "description": item.get("description"),
            "price": offers.get("price") or item.get("price"),
            "currency": offers.get("priceCurrency") or item.get("priceCurrency"),
            "stock": None,
            "category": item.get("category") or item.get("additionalType"),
            "brand": (item.get("brand") or {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"),
            "image_url": _image(item),
            "product_url": url,
            "attributes": {
                "source": "schema.org",
                "source_url": page_url,
                "offers": offers,
                "aggregateRating": item.get("aggregateRating"),
                "additionalProperty": item.get("additionalProperty"),
            },
        })
    return [r for r in rows if r.get("name")]


async def ingest_website(db, store, datasource, *, max_pages: int | None = None, max_depth: int = 5):
    limits = get_crawl_limits(store.plan)
    page_limit = max_pages or int(limits.get("max_pages", 100))
    crawler = WebsiteCrawler(max_pages=page_limit, max_depth=max_depth)
    pages = await crawler.crawl(datasource.connection_url)
    product_rows: list[dict] = []
    seen_products: set[str] = set()
    chunker = TextChunker()
    knowledge_created = knowledge_updated = 0
    now = datetime.utcnow()

    for page in pages:
        structured = page.get("structured_data") or []
        for row in extract_products_from_structured_data(structured, page["url"]):
            if row["id"] not in seen_products:
                seen_products.add(row["id"])
                product_rows.append(row)
        content = page.get("content") or ""
        if not content:
            continue
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = db.query(KnowledgePage).filter(KnowledgePage.store_id == store.id, KnowledgePage.url == page["url"]).first()
        page_type = classify_page(page["url"], page.get("title"), content, structured)
        if existing and existing.content_hash == content_hash:
            existing.status = "active"
            existing.crawled_at = now
            continue
        if existing:
            existing.title = page.get("title")
            existing.content = content
            existing.content_hash = content_hash
            existing.page_type = page_type
            existing.http_status = page.get("http_status")
            existing.status = "active"
            existing.crawled_at = now
            page_id = existing.id
            db.query(KnowledgeChunk).filter(KnowledgeChunk.page_id == page_id).delete(synchronize_session=False)
            knowledge_updated += 1
        else:
            existing = KnowledgePage(store_id=store.id, url=page["url"], title=page.get("title"), content=content, content_hash=content_hash, page_type=page_type, status="active", http_status=page.get("http_status"), crawled_at=now)
            db.add(existing)
            db.flush()
            page_id = existing.id
            knowledge_created += 1
        for index, chunk in enumerate(chunker.split(content)):
            db.add(KnowledgeChunk(store_id=store.id, page_id=page_id, chunk_index=index, content=chunk))

    result = None
    if product_rows:
        mapping = {field: field for field in ("id", "sku", "name", "description", "price", "stock", "category", "brand", "image_url", "product_url", "currency")}
        result = ProductSyncService(db).sync_rows(store.id, product_rows, mapping, full_sync=True, source_datasource_id=datasource.id)
    db.commit()
    return {"pages_found": len(pages), "products_found": len(product_rows), "knowledge_created": knowledge_created, "knowledge_updated": knowledge_updated, "products_created": result.created if result else 0, "products_updated": result.updated if result else 0, "products_unchanged": result.unchanged if result else 0, "errors": result.errors if result else []}
