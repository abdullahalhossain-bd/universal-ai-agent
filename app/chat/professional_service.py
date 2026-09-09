"""Professional commerce conversation layer on top of the dynamic chat service."""
from __future__ import annotations

import re
import uuid

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
    def _enrich_product_payload(store_id: str, db, products: list[dict]) -> list[dict]:
        from app.db.models import Product
        ids = [str(item.get("id")) for item in products if item.get("id")]
        if not ids:
            return products
        objects = db.query(Product).filter(Product.store_id == store_id, Product.id.in_(ids)).all()
        by_id = {str(product.id): product for product in objects}
        enriched = []
        for item in products:
            product = by_id.get(str(item.get("id")))
            payload = dict(item)
            if product is not None:
                payload["image_url"] = getattr(product, "image_url", None)
                payload["product_url"] = getattr(product, "product_url", None)
                payload["url"] = getattr(product, "product_url", None)
                payload["stock"] = getattr(product, "stock", item.get("stock"))
                payload["rating"] = getattr(product, "rating", item.get("rating"))
                payload["review_count"] = getattr(product, "review_count", item.get("review_count"))
                payload["sales_count"] = getattr(product, "sales_count", item.get("sales_count"))
                payload["bestseller_score"] = getattr(product, "bestseller_score", item.get("bestseller_score"))
                payload["attributes"] = getattr(product, "attributes", item.get("attributes")) or {}
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
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": self._enrich_product_payload(store_id, self.db, self._serialize_products(products)),
                    "sources": [],
                }
            referenced_product = self._get_referenced_product(store_id=store_id, session_id=session.id, message=message)

        is_link = self._is_link_request(message)
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
            return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": self._enrich_product_payload(store_id, self.db, self._serialize_products([referenced_product])), "sources": []}

        result = await super().handle(store_id=store_id, request=request)
        if not isinstance(result, dict):
            return result

        products = self._enrich_product_payload(store_id, self.db, result.get("products") or [])
        result["products"] = products
        is_recommendation = is_recommendation_query(message)
        is_followup = is_link or is_image or is_explanation
        if products and result.get("type") == "product_search" and not is_recommendation and not is_followup:
            result["message"] = self._professional_result_message(products)
        elif is_recommendation and products and not self._recommendation_has_support(products):
            result["message"] = "এই optionsগুলোর মধ্যে reliable rating, review বা sales evidence যথেষ্ট নেই। তাই অনুমান করে কোনো একটাকে best বলছি না 😊 চাইলে price, stock বা available features অনুযায়ী তুলনা করে দিতে পারি।"
        return result
