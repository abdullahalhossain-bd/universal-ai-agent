from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from app.knowledge.crawler import WebsiteCrawler


class WebsiteConnector:
    """Read products from an arbitrary merchant website without site-specific rules.

    Product data is discovered from the existing dynamic crawler/parser (Schema.org,
    JSON-LD and semantic microdata). The crawl is cached for the lifetime of one sync
    job so pagination does not repeatedly hit the merchant site.
    """

    supports_incremental_sync = False

    def __init__(self, root_url: str, *, max_pages: int = 100, max_depth: int = 3):
        self.root_url = root_url
        self.crawler = WebsiteCrawler(max_pages=max_pages, max_depth=max_depth)
        self._rows: list[dict] | None = None

    def _product_rows(self) -> list[dict]:
        if self._rows is not None:
            return self._rows

        import asyncio
        pages = asyncio.run(self.crawler.crawl(self.root_url))
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
                if isinstance(images, list):
                    image_url = images[0] if images else None
                    image_urls = images
                else:
                    image_url = images
                    image_urls = [images] if images else []
                external = product.get("sku") or product.get("productID") or product.get("url") or product.get("name")
                if not external:
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
        rows = self._product_rows()
        return rows[offset: offset + limit]

    def discover(self):
        return {"tables": [{"name": "website", "columns": [
            {"name": "id"}, {"name": "external_id"}, {"name": "sku"}, {"name": "name"},
            {"name": "description"}, {"name": "price"}, {"name": "compare_at_price"},
            {"name": "currency"}, {"name": "stock"}, {"name": "in_stock"}, {"name": "category"},
            {"name": "brand"}, {"name": "image_url"}, {"name": "image_urls"}, {"name": "product_url"},
            {"name": "attributes"},
        ]}]}
