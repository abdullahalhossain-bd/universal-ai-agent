"""Professional commerce conversation layer on top of the dynamic chat service."""
from __future__ import annotations

import re
import uuid
from urllib.parse import urljoin

from app.chat.dynamic_service import DynamicAttributeChatService
from app.products.recommendation import is_recommendation_query


class ProfessionalCommerceChatService(DynamicAttributeChatService):
    """Keep commerce conversations grounded, useful and customer-facing."""

    def _extract_product_index(self, message: str) -> int | None:
        index = super()._extract_product_index(message)
        if index is not None:
            return index
        normalized = re.sub(r"\s+", " ", message.casefold().strip())
        aliases = {
            "তৃতীয়": 3, "তৃতীয়টা": 3, "তৃতীয়টির": 3, "তৃতীয়টার": 3,
            "তৃতিয়": 3, "তৃতিয়টা": 3, "তৃতিয়টির": 3, "তৃতিয়টার": 3,
            "তৃতীয়টি": 3, "তৃতিয়টি": 3,
            "চতুর্থ": 4, "চতুর্থটা": 4, "চতুর্থটির": 4, "চতুর্থটার": 4,
            "পঞ্চম": 5, "পঞ্চমটা": 5, "পঞ্চমটির": 5, "পঞ্চমটার": 5,
        }
        for phrase, value in aliases.items():
            if phrase in normalized:
                return value
        return None

    @staticmethod
    def _resolve_media_url(value, base_url: str | None = None) -> str | None:
        """Return a browser-loadable absolute HTTP(S) media URL when possible."""
        if value is None:
            return None
        url = str(value).strip()
        if not url:
            return None
        if re.match(r"^https?://", url, flags=re.IGNORECASE):
            return url
        if base_url and re.match(r"^https?://", str(base_url).strip(), flags=re.IGNORECASE):
            return urljoin(str(base_url).rstrip("/") + "/", url.lstrip("/"))
        return None

    @staticmethod
    def _enrich_product_payload(store_id: str, db, products: list[dict]) -> list[dict]:
        from app.db.models import Product, Store
        ids = [str(item.get("id")) for item in products if item.get("id")]
        if not ids:
            return products
        store = db.query(Store).filter(Store.id == store_id).first()
        base_url = getattr(store, "website_url", None) if store is not None else None
        objects = db.query(Product).filter(Product.store_id == store_id, Product.id.in_(ids)).all()
        by_id = {str(product.id): product for product in objects}
        enriched = []
        for item in products:
            product = by_id.get(str(item.get("id")))
            payload = dict(item)
            if product is not None:
                db_image = getattr(product, "image_url", None)
                db_product_url = getattr(product, "product_url", None)
                # Do not overwrite a usable search payload with a null/empty DB value.
                payload["image_url"] = ProfessionalCommerceChatService._resolve_media_url(
                    db_image or item.get("image_url"), base_url
                )
                payload["product_url"] = ProfessionalCommerceChatService._resolve_media_url(
                    db_product_url or item.get("product_url") or item.get("url"), base_url
                )
                payload["url"] = payload["product_url"]
                payload["stock"] = getattr(product, "stock", item.get("stock"))
                payload["rating"] = getattr(product, "rating", item.get("rating"))
                payload["review_count"] = getattr(product, "review_count", item.get("review_count"))
                payload["sales_count"] = getattr(product, "sales_count", item.get("sales_count"))
                payload["bestseller_score"] = getattr(product, "bestseller_score", item.get("bestseller_score"))
                payload["attributes"] = getattr(product, "attributes", item.get("attributes")) or {}
            else:
                payload["image_url"] = ProfessionalCommerceChatService._resolve_media_url(item.get("image_url"), base_url)
                payload["product_url"] = ProfessionalCommerceChatService._resolve_media_url(item.get("product_url") or item.get("url"), base_url)
                payload["url"] = payload["product_url"]
            enriched.append(payload)
        return enriched

    @staticmethod
    def _professional_result_message(products: list[dict]) -> str:
        """Generate a short natural response without pretending to be a person."""
        names = [str(p.get("name") or p.get("title") or "product") for p in products[:3]]
        if len(products) == 1:
            return f"জি 😊 {names[0]} পাওয়া যাচ্ছে। নিচের card-এ দাম, stock আর product page-এর option দেখুন।"
        if len(names) == 2:
            return f"জি 😊 আপনার জন্য {names[0]} আর {names[1]}-সহ {len(products)}টা option পেলাম। যেটা পছন্দ হচ্ছে সেটায় click করে details দেখুন।"
        return f"জি 😊 আপনার জন্য {len(products)}টা option পেলাম—যেমন {', '.join(names[:-1])} এবং {names[-1]}। নিচের card-এ click করে details বা product page খুলতে পারবেন।"

    @staticmethod
    def _recommendation_has_support(products: list[dict]) -> bool:
        for product in products:
            rating = product.get("rating")
            reviews = product.get("review_count")
            sales = product.get("sales_count")
            bestseller = product.get("bestseller_score")
            try:
                if rating is not None and float(rating) >= 4.0 and reviews is not None and int(reviews) > 0:
                    return True
            except (TypeError, ValueError):
                pass
            try:
                if sales is not None and int(sales) > 0:
                    return True
            except (TypeError, ValueError):
                pass
            try:
                if bestseller is not None and float(bestseller) > 0:
                    return True
            except (TypeError, ValueError):
                pass
        return False

    @staticmethod
    def _is_catalog_attribute_question(message: str) -> bool:
        q = re.sub(r"\s+", " ", message.casefold().strip())
        if not q:
            return False
        question = any(term in q for term in (
            "ki ki", "what all", "what does", "which", "kon", "konta", "which one",
            "কি কি", "কী কী", "কোন", "কোনটা", "কোনটায়", "কোনটাতে",
        ))
        availability = any(term in q for term in (
            "ase", "ache", "available", "availability", "features", "feature", "spec", "specs",
            "আছে", "অ্যাভেইলেবল", "ফিচার", "স্পেসিফিকেশন",
        ))
        return question and availability

    @staticmethod
    def _catalog_attribute_message(products: list) -> str:
        if not products:
            return "দুঃখিত 😊 এই মুহূর্তে দেখানোর মতো product option নেই।"
        lines = ["অবশ্যই 😊 প্রতিটি option-এ কী কী আছে, সেটা নিচে দেখাচ্ছি। যেটা ভালো লাগবে সেটার card-এ click করলে আরও details দিতে পারব।"]
        for index, product in enumerate(products, 1):
            name = str(getattr(product, "name", None) or "Product")
            attrs = getattr(product, "attributes", None) or {}
            parts = []
            if isinstance(attrs, dict):
                for key, value in attrs.items():
                    if value is None or value == "":
                        continue
                    label = str(key).replace("_", " ").strip()
                    parts.append(f"{label}: {value}")
                    if len(parts) >= 5:
                        break
            if parts:
                lines.append(f"{index}. {name} — " + ", ".join(parts))
            else:
                lines.append(f"{index}. {name} — বিস্তারিত feature data নেই")
        return "\n".join(lines)

    async def handle(self, store_id: str, request):
        return await super().handle(store_id, request)
