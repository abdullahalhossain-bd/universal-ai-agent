from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_PRICE_RE = re.compile(r"(?:[$€£¥₹]|(?:USD|EUR|GBP|BDT|INR)\s*)?\s*\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{1,2})?", re.I)
_PRODUCT_TOKEN_RE = re.compile(r"(?:product|item|product-card|product-item|product-tile|product-grid|product-list|catalog|shop-item|woocommerce|shopify|add-to-cart|buy-now|price)", re.I)
_NAME_ATTRS = ("name", "product-name", "product_name", "title", "product-title", "product_title")
_PRICE_ATTRS = ("price", "sale-price", "regular-price", "product-price", "product_price")
_URL_ATTRS = ("url", "product-url", "product_url")
_SKU_ATTRS = ("sku", "product-id", "product_id", "productid", "itemid")


def _walk_products(value):
    found = []
    if isinstance(value, dict):
        typ = value.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if any(str(t).casefold() == "product" for t in types):
            found.append(value)
        for child in value.values():
            found.extend(_walk_products(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_products(child))
    return found


def _walk_product_like_json(value, parent_key: str = ""):
    """Discover product-shaped application state without merchant/vendor rules."""
    found = []
    if isinstance(value, dict):
        keys = {str(k).casefold() for k in value}
        name = value.get("name") or value.get("title") or value.get("productName")
        price = value.get("price")
        url = value.get("url") or value.get("productUrl") or value.get("link")
        image = value.get("image") or value.get("imageUrl") or value.get("thumbnail")
        if name and (price is not None or url or image) and (
            _PRODUCT_TOKEN_RE.search(parent_key) or {"sku", "price"} <= keys or "productid" in keys
        ):
            row = {"@type": "Product", "name": str(name).strip()}
            for src, dst in (("description", "description"), ("sku", "sku"), ("productId", "productID"),
                             ("category", "category"), ("brand", "brand"), ("image", "image"),
                             ("imageUrl", "image"), ("url", "url"), ("productUrl", "url"), ("link", "url")):
                if value.get(src) not in (None, ""):
                    row[dst] = value[src]
            if price is not None:
                row["offers"] = {"price": price, "priceCurrency": value.get("currency") or value.get("priceCurrency")}
            found.append(row)
        for key, child in value.items():
            found.extend(_walk_product_like_json(child, str(key)))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_product_like_json(child, parent_key))
    return found


def _dedupe_products(items: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for item in items:
        # Prefer the canonical product URL when available. A semantic parent
        # node and its nested product card can otherwise have different SKU
        # availability while representing the exact same catalog item.
        url = str(item.get("url") or "").strip().casefold()
        sku = str(item.get("sku") or "").strip().casefold()
        name = str(item.get("name") or "").strip().casefold()
        key = ("url", url) if url else (("sku", sku) if sku else ("name", name))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def extract_structured_data(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for script in soup.find_all("script"):
        raw = script.string or script.get_text()
        if not raw or len(raw) > 2_000_000:
            continue
        script_type = (script.get("type") or "").casefold()
        if "json" not in script_type and not raw.lstrip().startswith(("{", "[")):
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        items.extend(_walk_products(parsed))
        items.extend(_walk_product_like_json(parsed))

    for node in soup.select('[itemtype*="Product" i]'):
        row = {"@type": "Product"}
        for field in ("name", "description", "sku", "category", "brand", "image", "url"):
            el = node.select_one(f'[itemprop~="{field}"]')
            if el:
                row[field] = el.get("content") or el.get("href") or el.get("src") or el.get_text(" ", strip=True)
        price = node.select_one('[itemprop~="price"]')
        currency = node.select_one('[itemprop~="priceCurrency"]')
        if price:
            row["offers"] = {"price": price.get("content") or price.get_text(strip=True), "priceCurrency": currency.get("content") if currency else None}
        if row.get("name"):
            items.append(row)
    return _dedupe_products(items)


def _attr_value(node, names):
    if not node:
        return None
    for name in names:
        value = node.get(name)
        if isinstance(value, list):
            value = " ".join(value)
        if value and str(value).strip():
            return str(value).strip()
    return None


def _element_value(node, attrs):
    if not node:
        return None
    value = _attr_value(node, attrs)
    if value:
        return value
    for attr in ("data-name", "data-title", "aria-label", "content"):
        value = node.get(attr)
        if value and str(value).strip():
            return str(value).strip()
    text = node.get_text(" ", strip=True)
    return text or None


def _clean_price(value: str | None):
    if not value:
        return None
    match = _PRICE_RE.search(value.replace("\xa0", " "))
    return match.group(0).strip() if match else None


def _candidate_nodes(soup: BeautifulSoup):
    seen = set()
    selectors = [
        "[data-product-id]", "[data-product]", "[data-productid]", "[data-sku]",
        ".product", ".product-card", ".product-item", ".product-tile", ".product-grid-item",
        ".woocommerce-loop-product__link", "article", "li",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            if id(node) not in seen:
                seen.add(id(node)); yield node
    for node in soup.find_all(["div", "article", "li", "section"]):
        tokens = f"{' '.join(node.get('class', []))} {node.get('id', '')}"
        if _PRODUCT_TOKEN_RE.search(tokens) and id(node) not in seen:
            seen.add(id(node)); yield node


def extract_html_products(html: str, page_url: str | None = None) -> list[dict]:
    """Extract product candidates from ordinary HTML using vendor-neutral semantics."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for node in _candidate_nodes(soup):
        text = node.get_text(" ", strip=True)
        if not text or len(text) > 5000:
            continue
        tokens = f"{' '.join(node.get('class', []))} {node.get('id', '')}"
        name_el = node.select_one("[itemprop~=name], [data-product-name], [data-name], [data-title], h1, h2, h3, h4, h5, .title, .name")
        name = _element_value(name_el, _NAME_ATTRS)
        if not name and node.name in {"article", "li"}:
            link = node.select_one("a[href]")
            name = (link.get("aria-label") if link else None) or (link.get_text(" ", strip=True) if link else None)
        if not name or len(name) > 300:
            continue
        price_el = node.select_one("[itemprop~=price], [data-price], [data-product-price], .price, .sale-price, .amount")
        price = _clean_price(_element_value(price_el, _PRICE_ATTRS)) or _clean_price(text)
        link_el = node.select_one("a[href]")
        href = (link_el.get("href") if link_el else None) or _attr_value(node, _URL_ATTRS)
        product_url = urljoin(page_url, href) if href and page_url else href
        image_el = node.select_one("img[src], img[data-src], img[data-lazy-src]")
        image_url = None
        if image_el:
            image_url = image_el.get("src") or image_el.get("data-src") or image_el.get("data-lazy-src")
            if page_url and image_url:
                image_url = urljoin(page_url, image_url)
        sku = _attr_value(node, _SKU_ATTRS)
        sku_el = node.select_one("[data-sku], [itemprop~=sku]")
        if not sku and sku_el:
            sku = sku_el.get("content") or sku_el.get_text(" ", strip=True)

        score = 0
        if _PRODUCT_TOKEN_RE.search(tokens): score += 2
        if price: score += 2
        if product_url: score += 2
        if image_url: score += 1
        if sku: score += 1
        if any(t in text.casefold() for t in ("add to cart", "buy now", "shop now", "order now")): score += 2
        if score < 4 or not (price or product_url or image_url):
            continue
        results.append({
            "@type": "Product", "name": name, "sku": sku, "description": text[:1000],
            "offers": {"price": price} if price else {}, "image": image_url, "url": product_url,
            "_extraction": "semantic_html",
        })
    return _dedupe_products(results)


def extract_text(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def extract_metadata(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    description_tag = soup.find("meta", attrs={"name": "description"})
    return {"title": title_tag.get_text(strip=True) if title_tag else None,
            "description": description_tag.get("content") if description_tag else None,
            "headings": [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]}


def parse_page(html: str, page_url: str | None = None) -> dict:
    metadata = extract_metadata(html)
    structured = extract_structured_data(html)
    semantic = extract_html_products(html, page_url)
    return {**metadata, "content": extract_text(html), "structured_data": _dedupe_products(structured + semantic)}
