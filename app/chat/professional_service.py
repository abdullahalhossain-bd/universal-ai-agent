"""Professional commerce conversation layer on top of the dynamic chat service."""
from __future__ import annotations

import uuid

from app.chat.dynamic_service import DynamicAttributeChatService


class ProfessionalCommerceChatService(DynamicAttributeChatService):
    """Keep commerce conversations grounded, useful and customer-facing."""

    @staticmethod
    def _enrich_product_payload(store_id: str, db, products: list[dict]) -> list[dict]:
        """Guarantee frontend-safe image/link fields for product cards."""
        from app.db.models import Product

        ids = [str(item.get("id")) for item in products if item.get("id")]
        if not ids:
            return products

        objects = (
            db.query(Product)
            .filter(Product.store_id == store_id, Product.id.in_(ids))
            .all()
        )
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
            enriched.append(payload)
        return enriched

    @staticmethod
    def _professional_result_message(products: list[dict]) -> str:
        count = len(products)
        if count == 1:
            product = products[0]
            name = product.get("name") or product.get("title") or "Product"
            return f"{name}-এর details নিচে দেখুন। Price, stock, image এবং available product page link card-এ দেখানো হবে।"
        return (
            f"আপনার query অনুযায়ী {count}টি matching product পাওয়া গেছে। "
            "নিচে প্রতিটি product-এর price, stock, image এবং available product page link দেখুন।"
        )

    async def handle(self, store_id: str, request):
        message = getattr(request, "message", "").strip()
        conversation_id = getattr(request, "conversation_id", None)

        if conversation_id and self._is_bare_recommendation(message):
            session = self._get_or_create_session(store_id, conversation_id)
            context = self._load_product_context(session.id)
            if not (context.get("product_ids") or []):
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = (
                    "কোন product/category-এর মধ্যে best জানতে চান? "
                    "যেমন: laptop, phone, বা অন্য কোনো product।"
                )
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                self._log_analytics_event(store_id=store_id, message=message, intent="recommendation", result_count=0)
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": [],
                    "sources": [],
                }

        if not conversation_id and self._is_bare_recommendation(message):
            conversation_id = str(uuid.uuid4())
            request.conversation_id = conversation_id
            session = self._get_or_create_session(store_id, conversation_id)
            self._save_message(session_id=session.id, role="user", content=message)
            response_message = (
                "কোন product/category-এর মধ্যে best জানতে চান? "
                "যেমন: laptop, phone, বা অন্য কোনো product।"
            )
            self._save_message(session_id=session.id, role="assistant", content=response_message)
            self._log_analytics_event(store_id=store_id, message=message, intent="recommendation", result_count=0)
            return {
                "conversation_id": conversation_id,
                "type": "product_search",
                "message": response_message,
                "products": [],
                "sources": [],
            }

        result = await super().handle(store_id=store_id, request=request)
        if not isinstance(result, dict):
            return result

        products = self._enrich_product_payload(store_id, self.db, result.get("products") or [])
        result["products"] = products

        # Dynamic service already creates the special recommendation,
        # explanation, image and link responses. Do not overwrite them.
        is_recommendation = self._is_bare_recommendation(message) or any(
            token in message.casefold() for token in ("best", "top", "recommend", "সেরা", "ভালো")
        )
        is_followup = self._is_link_request(message) or self._is_image_request(message) or self._is_recommendation_explanation(message)
        if products and result.get("type") == "product_search" and not is_recommendation and not is_followup:
            result["message"] = self._professional_result_message(products)

        return result
