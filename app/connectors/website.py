from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from app.db.database import SessionLocal
from app.knowledge.chunk import KnowledgeChunk, KnowledgePage
from app.knowledge.chunker import TextChunker
from app.knowledge.crawler import WebsiteCrawler


class WebsiteConnector:
    """Generic website source backed by runtime crawling and structure discovery."""

    supports_incremental_sync = False

    def __init__(self, root_url: str, *, max_pages: int = 100, max_depth: int = 3):
        self.root_url = root_url
        self.crawler = WebsiteCrawler(max_pages=max_pages, max_depth=max_depth)
        self._rows: list[dict] | None = None
        self.store_id: str | None = None

    def _run_crawl(self) -> list[dict]:
        async def crawl():
            return await self.crawler.crawl(self.root_url)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(crawl())
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, crawl()).result()

    def _persist_knowledge(self, pages: list[dict]) -> None:
        if not pages or not self.store_id:
            return
        db = SessionLocal()
        chunker = TextChunker()
        try:
            for page in pages:
                content = page.get("content") or ""
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                existing = db.query(KnowledgePage).filter(
                    KnowledgePage.store_id == self.store_id,
                    KnowledgePage.url == page.get("url"),
                ).first()
                if existing and existing.content_hash == content_hash:
                    continue
                if existing:
                    existing.title = page.get("title")
                    existing.content = content
                    existing.content_hash = content_hash
                    existing.http_status = page.get("http_status")
                    page_id = existing.id
                    db.query(KnowledgeChunk).filter(KnowledgeChunk.page_id == page_id).delete(synchronize_session=False)
                else:
                    obj = KnowledgePage(
                        store_id=self.store_id,
                        url=page.get("url"),
                        title=page.get("title"),
                        content=content,
                        content_hash=content_hash,
                        http_status=page.get("http_status"),
                    )
                    db.add(obj)
                    db.flush()
                    page_id = obj.id
                for index, chunk in enumerate(chunker.split(content)):
                    db.add(KnowledgeChunk(store_id=self.store_id, page_id=page_id, chunk_index=index, content=chunk))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _product_rows(self) -> list[dict]:
        if self._rows is not None:
            return self._rows
        pages = self._run_crawl()
        self._persist_knowledge(pages)
        rows: list[dict] = []
        seen: set[str] = set()
        for page in pages:
            page_url = page.get("url") or self.root_url
            for product in page.get("structured_data") or []:
                offers = product.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                brand = product.get("brand")
                if isinstance(brand, dict):
                    brand = brand.get("name")
                images = product.get("image") or product.get("image_url")
                image_urls = images if isinstance(images, list) else ([images] if images else [])
                image_url = image_urls[0] if image_urls else None
                external = product.get("sku") or product.get("productID") or product.get("url") or product.get("name")
                if not external or not product.get("name"):
                    continue
                external = str(external)
                key = f"{urlparse(page_url).netloc}|{external}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "id": hashlib.sha256(key.encode()).hexdigest()[:40],
                    "external_id": external,
                    "sku": product.get("sku"),
                    "name": product.get("name"),
                    "description": product.get("description"),
                    "price": offers.get("price") if isinstance(offers, dict) else None,
                    "compare_at_price": None,
                    "currency": offers.get("priceCurrency") if isinstance(offers, dict) else None,
                    "stock": None,
                    "in_stock": None,
                    "category": product.get("category"),
                    "brand": brand,
                    "image_url": image_url,
                    "image_urls": image_urls,
                    "product_url": product.get("url") or page_url,
                    "attributes": {"source_url": page_url, "source_type": "website_structured_data"},
                })
        self._rows = rows
        return rows

    def fetch_product_rows(self, table_name, columns, *, limit=200, offset=0):
        return self._product_rows()[offset: offset + limit]

    def discover(self):
        return {"tables": [{"name": "website", "columns": [
            {"name": "id"}, {"name": "external_id"}, {"name": "sku"}, {"name": "name"},
            {"name": "description"}, {"name": "price"}, {"name": "compare_at_price"},
            {"name": "currency"}, {"name": "stock"}, {"name": "in_stock"}, {"name": "category"},
            {"name": "brand"}, {"name": "image_url"}, {"name": "image_urls"}, {"name": "product_url"},
            {"name": "attributes"},
        }]}
