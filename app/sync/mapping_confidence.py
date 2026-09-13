"""Confidence-scored schema inference for arbitrary merchant columns."""
from __future__ import annotations

import re
from collections import Counter

ALIASES = {
    "id": ("id", "productid", "product_id", "sku", "itemid", "item_id", "code", "productcode", "product_code"),
    "name": ("name", "productname", "product_name", "title", "producttitle", "product_title", "itemname", "item_name"),
    "description": ("description", "productdescription", "product_description", "details", "summary", "shortdescription"),
    "price": ("price", "saleprice", "sale_price", "sellingprice", "selling_price", "regularprice", "regular_price", "amount", "cost"),
    "stock": ("stock", "quantity", "qty", "inventory", "inventoryquantity", "inventory_quantity", "stockquantity", "stock_quantity", "availablequantity", "available_quantity"),
    "category": ("category", "categoryname", "category_name", "productcategory", "product_category", "type", "producttype", "product_type"),
    "currency": ("currency", "currencycode", "currency_code", "pricecurrency", "price_currency"),
    "image_url": ("image_url", "image", "images", "main_image", "mainimage", "image_src", "imagesource", "imageurl", "thumbnail", "thumbnail_url", "featured_image", "photo", "picture", "productimage", "primaryimage", "coverimage"),
    "product_url": ("product_url", "producturl", "url", "link", "product_link", "productlink", "permalink", "product_page", "productpage", "product_page_url", "web_url", "shop_url", "href", "product_href"),
    "updated_at": ("updated_at", "updatedat", "modified_at", "modifiedat", "last_updated", "lastmodified", "updated"),
    "created_at": ("created_at", "createdat", "date_created", "created", "published_at"),
}


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _url_like(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().casefold()
    return text.startswith(("http://", "https://", "/", "//")) or ("." in text and " " not in text and len(text) > 5)


def _image_like(value: object) -> bool:
    if isinstance(value, (list, tuple, dict)):
        return True
    text = str(value or "").casefold()
    return any(x in text for x in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", "image"))


def _name_score(column: str, field: str) -> float:
    key = _key(column)
    aliases = {_key(a) for a in ALIASES.get(field, ())}
    if key in aliases:
        return 0.99
    tokens = [a for a in aliases if len(a) >= 4 and (a in key or key in a)]
    return min(0.92, 0.70 + 0.04 * max((len(x) for x in tokens), default=0)) if tokens else 0.0


def _value_score(field: str, values: list[object]) -> float:
    values = [v for v in values if v not in (None, "")][:50]
    if not values:
        return 0.0
    if field == "product_url":
        return sum(_url_like(v) for v in values) / len(values) * 0.20
    if field == "image_url":
        return sum(_image_like(v) for v in values) / len(values) * 0.20
    if field in {"price", "stock"}:
        good = 0
        for v in values:
            try:
                float(str(v).replace(",", ""))
                good += 1
            except (TypeError, ValueError):
                pass
        return good / len(values) * 0.20
    if field == "currency":
        return sum(bool(re.fullmatch(r"[A-Za-z]{3}", str(v).strip())) for v in values) / len(values) * 0.20
    if field in {"id", "name"}:
        unique = len({str(v).strip() for v in values}) / len(values)
        return min(0.20, unique * 0.20)
    return 0.05


def infer_mapping(raw: dict, previous: dict | None = None) -> dict:
    columns = [str(c) for c in raw.keys()]
    used: set[str] = set()
    previous = previous or {}
    candidates = {}
    for field, aliases in ALIASES.items():
        ranked = []
        for column in columns:
            if column in used:
                continue
            score = _name_score(column, field) + _value_score(field, [raw.get(column)])
            old = previous.get(field)
            old = old.get("column") if isinstance(old, dict) else old
            if old == column:
                score += 0.05
            ranked.append((min(score, 1.0), column))
        ranked.sort(reverse=True)
        if ranked and ranked[0][0] >= 0.80:
            score, column = ranked[0]
            candidates[field] = {"column": column, "confidence_pct": round(score * 100, 1)}
            used.add(column)
    return candidates


def discover_mapping_with_confidence(raw: dict, previous: dict | None = None) -> dict:
    return infer_mapping(raw, previous)
