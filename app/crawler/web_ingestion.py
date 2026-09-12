from __future__ import annotations

import hashlib
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urljoin

import redis.asyncio as redis

from app.core.config import settings
from app.crawler.classifier import classify_page
from app.crawler.limits import get_crawl_limits
from app.knowledge.chunk import KnowledgeChunk, KnowledgePage
from app.knowledge.chunker import TextChunker
from app.knowledge.crawler import WebsiteCrawler
from app.sync.service import ProductSyncService
from app.db.database import SessionLocal
from app.db.models import DataSource, Store, SyncRun


def _canonical_url(url: str, base: str) -> str:
    return urljoin(base, url).split("#", 1)[0]


def _product_id(url: str, fallback: str | None = None) -> str:
    return "web_" + hashlib.sha256((url or fallback or "").strip().encode("utf-8")).hexdigest()[:96]


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
        availability = str(offers.get("availability") or "").casefold()
        stock = 0 if "outofstock" in availability else None
        rows.append({
            "id": _product_id(url, item.get("sku") or item.get("mpn") or item.get("name")),
            "sku": item.get("sku") or item.get("mpn"),
            "name": item.get("name"),
            "description": item.get("description"),
            "price": offers.get("price") or item.get("price"),
            "currency": offers.get("priceCurrency") or item.get("priceCurrency"),
            "stock": stock,
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
    return [row for row in rows if row.get("name")]


async def ingest_website(db, store, datasource, *, max_pages: int | None = None, max_depth: int | None = None):
    limits = get_crawl_limits(store.plan)
    page_limit = max_pages or int(limits.get("max_pages", settings.crawler_max_pages))
    depth_limit = settings.crawler_max_depth if max_depth is None else max(0, int(max_depth))
    progress_key = f"crawl_progress:{store.id}:{datasource.id}"
    progress = redis.from_url(settings.redis_url, decode_responses=True)
    last_progress = {"pages_crawled": 0, "pages_failed": 0, "queued": 0, "max_pages": page_limit}

    async def report(state):
        nonlocal last_progress
        last_progress = {k: v for k, v in state.items() if v is not None}
        last_progress.setdefault("status", "running")
        payload = {k: str(v) for k, v in last_progress.items()}
        await progress.hset(progress_key, mapping=payload)
        await progress.expire(progress_key, 86400)

    await report(last_progress)
    try:
        crawler = WebsiteCrawler(
            max_pages=page_limit,
            max_depth=depth_limit,
            concurrency=settings.crawler_concurrency,
            requests_per_second=settings.crawler_requests_per_second,
            max_retries=settings.crawler_max_retries,
        )
        pages = await crawler.crawl(datasource.connection_url, progress_callback=report)
        product_rows = []
        seen_products = set()
        chunker = TextChunker()
        knowledge_created = knowledge_updated = 0
        knowledge_unchanged = 0
        now = datetime.utcnow()

        for page in pages:
            structured = page.get("structured_data") or []
            for row in extract_products_from_structured_data(structured, page["url"]):
                if row["id"] not in seen_products:
                    seen_products.add(row["id"])
                    product_rows.append(row)

            content = (page.get("content") or "").strip()
            if not content:
                continue
            canonical_url = _canonical_url(page["url"], datasource.connection_url)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            existing = db.query(KnowledgePage).filter(
                KnowledgePage.store_id == store.id,
                KnowledgePage.url == canonical_url,
            ).first()
            page_type = classify_page(canonical_url, page.get("title"), content, structured)

            if existing and existing.content_hash == content_hash:
                existing.status = "active"
                existing.crawled_at = now
                knowledge_unchanged += 1
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
                existing = KnowledgePage(
                    store_id=store.id,
                    url=canonical_url,
                    title=page.get("title"),
                    content=content,
                    content_hash=content_hash,
                    page_type=page_type,
                    status="active",
                    http_status=page.get("http_status"),
                    crawled_at=now,
                )
                db.add(existing)
                db.flush()
                page_id = existing.id
                knowledge_created += 1

            for index, chunk in enumerate(chunker.split(content)):
                clean_chunk = (chunk or "").strip()
                if clean_chunk:
                    db.add(KnowledgeChunk(store_id=store.id, page_id=page_id, chunk_index=index, content=clean_chunk))

        result = None
        if product_rows:
            mapping = {field: field for field in ("id", "sku", "name", "description", "price", "stock", "category", "brand", "image_url", "product_url", "currency")}
            result = ProductSyncService(db).sync_rows(
                store.id,
                product_rows,
                mapping,
                full_sync=False,
                source_datasource_id=datasource.id,
            )

        db.commit()
        errors = list(result.errors) if result else []
        final = {
            "pages_found": len(pages),
            "pages_failed": int(last_progress.get("pages_failed", 0)),
            "products_found": len(product_rows),
            "knowledge_created": knowledge_created,
            "knowledge_updated": knowledge_updated,
            "knowledge_unchanged": knowledge_unchanged,
            "products_created": result.created if result else 0,
            "products_updated": result.updated if result else 0,
            "products_unchanged": result.unchanged if result else 0,
            "errors": errors,
        }
        await report({**final, "queued": 0, "status": "partial" if errors or final["pages_failed"] else "success"})
        return final
    finally:
        await progress.aclose()


async def run_website_sync(job: dict):
    db = SessionLocal()
    started = datetime.utcnow()
    run = None
    try:
        store_id = job.get("store_id") or job.get("tenant_id")
        datasource_id = job.get("datasource_id")
        ds = db.query(DataSource).filter(
            DataSource.id == datasource_id,
            DataSource.store_id == store_id,
            DataSource.active.is_(True),
        ).first()
        store = db.query(Store).filter(Store.id == store_id).first()
        if not ds or ds.connector_type != "website" or not ds.connection_url:
            raise LookupError("active website datasource not found")
        if store is None:
            raise LookupError("store not found")

        run = SyncRun(
            store_id=store_id,
            datasource_id=datasource_id,
            status="running",
            sync_mode="website_full",
            started_at=started,
        )
        db.add(run)
        db.commit()
        result = await ingest_website(db, store, ds)
        status = "success" if not result["errors"] and not result["pages_failed"] else "partial"
        run.status = status
        run.finished_at = datetime.utcnow()
        run.products_seen = result["products_found"]
        run.created = result["products_created"]
        run.updated = result["products_updated"]
        run.unchanged = result["products_unchanged"]
        run.quality_report = result
        run.error = "; ".join(result["errors"]) if result["errors"] else None
        ds.last_sync_at = datetime.utcnow()
        ds.last_sync_status = status
        ds.last_sync_error = run.error
        db.commit()
        return SimpleNamespace(
            created=result["products_created"],
            updated=result["products_updated"],
            unchanged=result["products_unchanged"],
            errors=[],
            data_quality={"terminal": "partial_website_sync"} if status == "partial" else {},
        )
    except Exception as exc:
        db.rollback()
        if run is not None:
            run.status = "error"
            run.finished_at = datetime.utcnow()
            run.error = str(exc)[:4000]
            db.add(run)
            db.commit()
        raise
    finally:
        db.close()
