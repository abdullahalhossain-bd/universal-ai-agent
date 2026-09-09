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
        """Use natural sales-assistant language instead of search-engine terminology."""
        if len(products) == 1:
            product = products[0]
            name = product.get("name") or product.get("title") or "এই product"
            return f"জি, {name} পাওয়া যাচ্ছে 😊 বিস্তারিত নিচে দেখুন।"
        return "জি, আছে 😊 আপনার জন্য available optionগুলো নিচে দিলাম। পছন্দেরটা দেখুন।"

    @staticmethod
    def _recommendation_has_support(products: list[dict]) -> bool:
        """Only make a strong 'best' claim when the catalog has usable evidence."""
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
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

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
            return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

        session = None
        referenced_product = None
        if conversation_id:
            session = self._get_or_create_session(store_id, conversation_id)
            referenced_product = self._get_referenced_product(
                store_id=store_id,
                session_id=session.id,
                message=message,
            )

        is_link = self._is_link_request(message)
        is_image = self._is_image_request(message)
        is_explanation = self._is_recommendation_explanation(message)

        # A follow-up that needs a product must never silently become a fresh
        # search. Ask for the missing reference instead of showing unrelated items.
        if (is_link or is_image or is_explanation) and referenced_product is None:
            if session is not None:
                self._save_message(session_id=session.id, role="user", content=message)
            response_message = (
                "অবশ্যই 😊 কোন product-এর কথা বলছেন? "
                "যেমন product-এর নাম বা তালিকার নম্বরটি বলুন।"
            )
            if session is not None:
                self._save_message(session_id=session.id, role="assistant", content=response_message)
            return {
                "conversation_id": conversation_id or str(uuid.uuid4()),
                "type": "product_search",
                "message": response_message,
                "products": [],
                "sources": [],
            }

        if session is not None and referenced_product is not None and (is_link or is_image or is_explanation):
            self._save_message(session_id=session.id, role="user", content=message)
            name = self._format_product_name(referenced_product)
            if is_image:
                response_message = (
                    f"অবশ্যই 😊 {name}-এর image নিচে দেখুন।"
                    if getattr(referenced_product, "image_url", None)
                    else f"দুঃখিত, {name}-এর image এখন available নেই।"
                )
            elif is_link:
                response_message = (
                    f"অবশ্যই 😊 {name}-এর product page-এর link নিচের card-এ দিলাম।"
                    if getattr(referenced_product, "product_url", None)
                    else f"দুঃখিত, {name}-এর product link এখন available নেই।"
                )
            else:
                context_products = self._context_products(store_id, session.id)
                response_message = self._recommendation_explanation(
                    referenced_product,
                    context_products or [referenced_product],
                )
            self._save_message(session_id=session.id, role="assistant", content=response_message)
            return {
                "conversation_id": conversation_id,
                "type": "product_search",
                "message": response_message,
                "products": self._serialize_products([referenced_product]),
                "sources": [],
            }

        result = await super().handle(store_id=store_id, request=request)
        if not isinstance(result, dict):
            return result

        products = self._enrich_product_payload(store_id, self.db, result.get("products") or [])
        result["products"] = products

        is_recommendation = self._is_bare_recommendation(message) or any(
            token in message.casefold() for token in ("best", "top", "recommend", "সেরা", "ভালো")
        )
        is_followup = is_link or is_image or is_explanation
        if products and result.get("type") == "product_search" and not is_recommendation and not is_followup:
            result["message"] = self._professional_result_message(products)
        elif is_recommendation and products and not self._recommendation_has_support(products):
            result["message"] = (
                "এই optionগুলোর মধ্যে নির্ভরযোগ্য rating, review বা sales information যথেষ্ট নেই। "
                "তাই অনুমান করে কোনো একটাকে সেরা বলছি না। চাইলে price, stock বা available features দেখে তুলনা করে দিতে পারি।"
            )

        return result
