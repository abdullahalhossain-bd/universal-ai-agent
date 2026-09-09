"""Professional commerce conversation layer on top of the dynamic chat service."""
from __future__ import annotations

import re
import uuid
from urllib.parse import urljoin

from app.chat.dynamic_service import DynamicAttributeChatService
from app.chat.intent_semantics import classify_product_link_request, parse_llm_link_intent
from app.images.url_verifier import verify_image_urls
from app.products.recommendation import is_recommendation_query


class ProfessionalCommerceChatService(DynamicAttributeChatService):
    """Keep commerce conversations grounded, useful and customer-facing."""

    def _extract_product_index(self, message: str) -> int | None:
        """Extract an index only when the user explicitly references a list position."""
        text = re.sub(r"\s+", " ", message.casefold().strip())
        text = text.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))

        explicit_patterns = (
            r"(?:product\s*)?#\s*(\d+)\b",
            r"(?:product\s*)?(\d+)\s*(?:number|no\.?|নম্বর|নং)",
            r"(?:number|no\.?|নম্বর|নং)\s*(\d+)\b",
            r"(\d+)(?:st|nd|rd|th)\s+(?:one|product|item)\b",
            r"(?:one|product|item)\s*(?:number|no\.?)\s*(\d+)\b",
        )
        for pattern in explicit_patterns:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                if 1 <= value <= 100:
                    return value

        aliases = {
            "প্রথম": 1, "প্রথমটা": 1, "প্রথমটির": 1, "প্রথমটার": 1,
            "দ্বিতীয়": 2, "দ্বিতীয়টা": 2, "দ্বিতীয়টির": 2, "দ্বিতীয়টার": 2,
            "দ্বিতীয়": 2, "দ্বিতীয়টা": 2, "দ্বিতীয়টির": 2, "দ্বিতীয়টার": 2,
            "তৃতীয়": 3, "তৃতীয়টা": 3, "তৃতীয়টির": 3, "তৃতীয়টার": 3,
            "তৃতিয়": 3, "তৃতিয়টা": 3, "তৃতিয়টির": 3, "তৃতিয়টার": 3,
            "তৃতীয়": 3, "তৃতীয়টা": 3, "তৃতীয়টির": 3, "তৃতীয়টার": 3,
            "চতুর্থ": 4, "চতুর্থটা": 4, "চতুর্থটির": 4, "চতুর্থটার": 4,
            "পঞ্চম": 5, "পঞ্চমটা": 5, "পঞ্চমটির": 5, "পঞ্চমটার": 5,
            "first": 1, "first one": 1, "second": 2, "second one": 2,
            "third": 3, "third one": 3, "fourth": 4, "fourth one": 4,
            "fifth": 5, "fifth one": 5,
        }
        for phrase, value in aliases.items():
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
                return value
        return None

    async def _detect_product_link_request(self, message: str, has_product_context: bool) -> bool:
        """Use cheap semantic signals first and the existing LLM stack only when ambiguous."""
        local = classify_product_link_request(message)
        if local is not None:
            return local
        if not has_product_context:
            return False
        try:
            response_service = self._shared_llm_stack()
            generator = getattr(response_service, "llm_generator", None)
            router = getattr(generator, "provider_router", None)
            if router is None:
                return False
            result = await router.generate(messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify whether the user is asking for the purchase/product page, "
                        "buying location, ordering destination, or product URL of a product. "
                        "Return only TRUE or FALSE. Do not classify store office/location, shipping, "
                        "delivery, return, refund, or generic knowledge questions as TRUE."
                    ),
                },
                {"role": "user", "content": message[:1000]},
            ])
            return parse_llm_link_intent(str(result.get("text", ""))) is True
        except Exception:
            return False

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
        """Enrich payloads from the DB row with the exact same product ID."""
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
            product_id = str(item.get("id")) if item.get("id") is not None else None
            product = by_id.get(product_id) if product_id else None
            payload = dict(item)
            if product is not None:
                db_image = getattr(product, "image_url", None)
                db_product_url = getattr(product, "product_url", None)
                payload["id"] = str(product.id)
                payload["image_url"] = ProfessionalCommerceChatService._resolve_media_url(db_image, base_url)
                payload["product_url"] = ProfessionalCommerceChatService._resolve_media_url(db_product_url, base_url)
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
    async def _verify_product_images(products: list[dict]) -> list[dict]:
        """Keep only exact-product image URLs that are safe and actually serve images."""
        urls = [product.get("image_url") for product in products]
        verification = await verify_image_urls(urls)
        verified = []
        for product in products:
            payload = dict(product)
            url = payload.get("image_url")
            ok = bool(url and verification.get(url, False))
            payload["image_verified"] = ok
            if not ok:
                payload["image_url"] = None
            verified.append(payload)
        return verified

    @staticmethod
    async def _prepare_products(store_id: str, db, products: list[dict]) -> list[dict]:
        """Resolve exact DB media first, then verify image reachability before API output."""
        enriched = ProfessionalCommerceChatService._enrich_product_payload(store_id, db, products)
        return await ProfessionalCommerceChatService._verify_product_images(enriched)

    @staticmethod
    def _professional_result_message(products: list[dict]) -> str:
        names = [str(p.get("name") or p.get("title") or "product") for p in products[:3]]
        if len(products) == 1:
            return f"জি 😊 {names[0]} পাওয়া যাচ্ছে। নিচের card-এ দাম, stock আর product page-এর option দেখুন।"
        if len(names) == 2:
            return f"জি 😊 আপনার জন্য {names[0]} আর {names[1]}-সহ {len(products)}টা option পেলাম। যেটা পছন্দ হচ্ছে সেটায় click করে details দেখুন।"
        return f"জি 😊 আপনার জন্য {len(products)}টা option পেলাম—যেমন {', '.join(names[:-1])} এবং {names[-1]}। নিচের card-এ click করে details বা product page খুলতে পারবেন।"

    @staticmethod
    def _recommendation_has_support(products: list[dict]) -> bool:
        for product in products:
            rating, reviews, sales, bestseller = product.get("rating"), product.get("review_count"), product.get("sales_count"), product.get("bestseller_score")
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
        question = any(term in q for term in ("ki ki", "what all", "what does", "which", "kon", "konta", "which one", "কি কি", "কী কী", "কোন", "কোনটা", "কোনটায়", "কোনটাতে"))
        availability = any(term in q for term in ("ase", "ache", "available", "availability", "features", "feature", "spec", "specs", "আছে", "অ্যাভেইলেবল", "ফিচার", "স্পেসিফিকেশন"))
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
                    parts.append(f"{str(key).replace('_', ' ').strip()}: {value}")
                    if len(parts) >= 5:
                        break
            lines.append(f"{index}. {name} — " + ", ".join(parts) if parts else f"{index}. {name} — বিস্তারিত feature data নেই")
        return "\n".join(lines)

    async def handle(self, store_id: str, request):
        message = getattr(request, "message", "").strip()
        conversation_id = getattr(request, "conversation_id", None)

        if conversation_id and self._is_bare_recommendation(message):
            session = self._get_or_create_session(store_id, conversation_id)
            context = self._load_product_context(session.id)
            if not (context.get("product_ids") or []):
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = "অবশ্যই 😊 কোন product বা category-এর মধ্যে best option চান? নামটা বললেই আমি options দেখে দিচ্ছি।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                self._log_analytics_event(store_id=store_id, message=message, intent="recommendation", result_count=0)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

        if not conversation_id and self._is_bare_recommendation(message):
            conversation_id = str(uuid.uuid4())
            request.conversation_id = conversation_id
            session = self._get_or_create_session(store_id, conversation_id)
            self._save_message(session_id=session.id, role="user", content=message)
            response_message = "অবশ্যই 😊 কোন product বা category-এর মধ্যে best option চান? নামটা বললেই আমি options দেখে দিচ্ছি।"
            self._save_message(session_id=session.id, role="assistant", content=response_message)
            self._log_analytics_event(store_id=store_id, message=message, intent="recommendation", result_count=0)
            return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

        session = None
        referenced_product = None
        if conversation_id:
            session = self._get_or_create_session(store_id, conversation_id)
            context = self._load_product_context(session.id)
            if context.get("product_ids") and self._is_catalog_attribute_question(message):
                products = self._context_products(store_id, session.id)
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = self._catalog_attribute_message(products)
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                prepared = await self._prepare_products(store_id, self.db, self._serialize_products(products))
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": prepared, "sources": []}
            referenced_product = self._get_referenced_product(store_id=store_id, session_id=session.id, message=message)

        has_context = bool(conversation_id and (referenced_product or self._load_product_context(session.id).get("product_ids")))
        is_link = await self._detect_product_link_request(message, has_context)
        is_image = self._is_image_request(message)
        is_explanation = self._is_recommendation_explanation(message)

        if (is_link or is_image or is_explanation) and referenced_product is None:
            if session is not None:
                self._save_message(session_id=session.id, role="user", content=message)
            response_message = "অবশ্যই 😊 কোন product-এর কথা বলছেন? নাম বা আগের list-এর নম্বরটা বললেই ঠিক সেটার তথ্য দেখাচ্ছি।"
            if session is not None:
                self._save_message(session_id=session.id, role="assistant", content=response_message)
            return {"conversation_id": conversation_id or str(uuid.uuid4()), "type": "product_search", "message": response_message, "products": [], "sources": []}

        if session is not None and referenced_product is not None and (is_link or is_image or is_explanation):
            self._save_message(session_id=session.id, role="user", content=message)
            name = self._format_product_name(referenced_product)
            if is_image:
                response_message = f"অবশ্যই 😊 {name}-এর image নিচে দিলাম।" if getattr(referenced_product, "image_url", None) else f"দুঃখিত, {name}-এর image এখন available নেই।"
            elif is_link:
                response_message = f"অবশ্যই 😊 {name}-এর product page-এর link নিচের card-এ দিলাম।" if getattr(referenced_product, "product_url", None) else f"দুঃখিত, {name}-এর product link এখন available নেই।"
            else:
                context_products = self._context_products(store_id, session.id)
                response_message = self._recommendation_explanation(referenced_product, context_products or [referenced_product])
            self._save_message(session_id=session.id, role="assistant", content=response_message)
            prepared = await self._prepare_products(store_id, self.db, self._serialize_products([referenced_product]))
            return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": prepared, "sources": []}

        result = await super().handle(store_id=store_id, request=request)
        if not isinstance(result, dict):
            return result
        products = await self._prepare_products(store_id, self.db, result.get("products") or [])
        result["products"] = products
        is_recommendation = is_recommendation_query(message)
        is_followup = is_link or is_image or is_explanation
        if products and result.get("type") == "product_search" and not is_recommendation and not is_followup:
            result["message"] = self._professional_result_message(products)
        elif is_recommendation and products and not self._recommendation_has_support(products):
            result["message"] = "এই optionsগুলোর মধ্যে reliable rating, review বা sales evidence যথেষ্ট নেই। তাই অনুমান করে কোনো একটাকে best বলছি না 😊 চাইলে price, stock বা available features অনুযায়ী তুলনা করে দিতে পারি।"
        return result
