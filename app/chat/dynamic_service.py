"""ChatService variant with first-class merchant-defined attributes and recommendations."""
from __future__ import annotations

from contextvars import ContextVar
import logging
import re

from sqlalchemy import and_, or_

from app.chat.service import ChatService
from app.chat.models import ChatMessage
from app.db.models import Product
from app.products.attribute_filters import apply_attribute_filters
from app.products.recommendation import is_recommendation_query, rank_products
from app.search.behavior_learning import get_behavior_scores, record_event
from app.search.stopwords import STOPWORDS
from app.search.synonyms import expand_terms

logger = logging.getLogger(__name__)
_RECOMMENDATION_CONTEXT: ContextVar[str] = ContextVar("recommendation_context", default="")
_BEHAVIOR_SCORES: ContextVar[dict] = ContextVar("behavior_scores", default={})


class DynamicAttributeChatService(ChatService):
    """ChatService with structured attributes and adaptive recommendation ranking."""

    @staticmethod
    def _text_terms(product_name: str | None) -> list[str]:
        terms = []
        for token in (product_name or "").split():
            token = token.strip(".,!?;:()[]{}\"'")
            if len(token) < 2 or token.casefold() in STOPWORDS or token.isdigit():
                continue
            terms.append(token)
        return terms

    def _build_product_text_conditions(self, product_name: str | None):
        groups = []
        for term in self._text_terms(product_name):
            synonyms = expand_terms([term]) or [term]
            groups.append(or_(*[
                or_(Product.name.ilike(f"%{synonym}%"), Product.description.ilike(f"%{synonym}%"), Product.category.ilike(f"%{synonym}%"))
                for synonym in synonyms
            ]))
        return groups

    def _save_product_context(self, session_id, products, query, filters=None, offset=0):
        if filters is not None and not isinstance(filters, dict):
            filters = {
                "min_price": getattr(filters, "min_price", None),
                "max_price": getattr(filters, "max_price", None),
                "in_stock": getattr(filters, "in_stock", False),
                "product_name": getattr(filters, "product_name", None),
                "recommendation": getattr(filters, "recommendation", False),
                "attributes": getattr(filters, "attributes", {}) or {},
            }
        super()._save_product_context(session_id=session_id, products=products, query=query, filters=filters, offset=offset)

    def _rank(self, store_id: str, products: list[Product], query: str) -> list[Product]:
        if not products or not is_recommendation_query(query):
            return products
        scores = get_behavior_scores(self.db, store_id, [str(p.id) for p in products])
        _BEHAVIOR_SCORES.set(scores)
        return rank_products(products, query, behavior_scores=scores)

    @staticmethod
    def _is_bare_recommendation(message: str) -> bool:
        normalized = message.casefold().strip()
        normalized = re.sub(r"[?!.:,;]+", " ", normalized)
        tokens = [t for t in re.split(r"\s+", normalized) if t]
        if not tokens or len(tokens) > 5:
            return False
        generic = {
            "best", "top", "recommend", "recommended", "suggest", "suggestion",
            "konta", "kon", "ta", "one", "which", "is", "the", "please",
            "কোনটা", "কোনটি", "কোন", "টা", "টি", "সেরা", "ভালো", "ভাল", "সর্বোত্তম",
        }
        return all(token in generic for token in tokens) and any(
            token in {"best", "top", "recommend", "recommended", "suggest", "suggestion", "সেরা", "ভালো", "ভাল", "সর্বোত্তম"}
            for token in tokens
        )

    @staticmethod
    def _is_link_request(message: str) -> bool:
        q = message.casefold().strip()
        return any(term in q for term in (
            "link", "url", "website", "product page", "লিংক", "লিঙ্ক", "ওয়েবসাইট", "ওয়েবসাইট",
        ))

    @staticmethod
    def _is_image_request(message: str) -> bool:
        q = message.casefold().strip()
        return any(term in q for term in (
            "image", "photo", "picture", "pic", "ছবি", "ইমেজ", "ফটো",
        ))

    @staticmethod
    def _is_recommendation_explanation(message: str) -> bool:
        q = message.casefold().strip()
        patterns = (
            "kemne sera", "kemon kore sera", "ken sera", "karon ki", "why best",
            "how best", "how is it best", "why is it best", "best keno",
            "কেন সেরা", "কিভাবে সেরা", "কীভাবে সেরা", "কেন best", "কীভাবে best",
            "কেন ভালো", "কিভাবে ভালো", "basis ki", "basis", "reason",
        )
        return any(pattern in q for pattern in patterns)

    def _context_products(self, store_id: str, session_id: str) -> list[Product]:
        context = self._load_product_context(session_id)
        ids = context.get("product_ids") or []
        return self._get_products_by_ids(store_id, ids)

    @staticmethod
    def _recommendation_evidence(products: list[Product]) -> bool:
        """Require meaningful catalog evidence before making a strong recommendation claim."""
        for product in products:
            try:
                rating = float(getattr(product, "rating", None)) if getattr(product, "rating", None) is not None else None
                reviews = int(getattr(product, "review_count", None)) if getattr(product, "review_count", None) is not None else 0
                if rating is not None and rating >= 4.0 and reviews >= 5:
                    return True
            except (TypeError, ValueError):
                pass
            try:
                if int(getattr(product, "sales_count", None) or 0) >= 10:
                    return True
            except (TypeError, ValueError):
                pass
            try:
                if float(getattr(product, "bestseller_score", None) or 0) >= 0.8:
                    return True
            except (TypeError, ValueError):
                pass
        return False

    @staticmethod
    def _format_product_name(product: Product | None) -> str:
        return str(getattr(product, "name", "Product") or "Product") if product else "Product"

    def _recommendation_explanation(self, product: Product, candidates: list[Product]) -> str:
        reasons = []
        rating = getattr(product, "rating", None)
        reviews = getattr(product, "review_count", None)
        sales = getattr(product, "sales_count", None)
        bestseller = getattr(product, "bestseller_score", None)
        try:
            if rating is not None and float(rating) > 0:
                reasons.append(f"rating {float(rating):.1f}/5")
        except (TypeError, ValueError):
            pass
        try:
            if reviews is not None and int(reviews) > 0:
                reasons.append(f"{int(reviews):,} reviews")
        except (TypeError, ValueError):
            pass
        try:
            if sales is not None and int(sales) > 0:
                reasons.append(f"{int(sales):,} sales")
        except (TypeError, ValueError):
            pass
        try:
            if bestseller is not None and float(bestseller) > 0:
                reasons.append("bestseller হিসেবে ভালো performance")
        except (TypeError, ValueError):
            pass

        if reasons and self._recommendation_evidence([product]):
            return (
                f"{self._format_product_name(product)}-কে আমি এগিয়ে রাখছি কারণ "
                + ", ".join(reasons)
                + ". তাই available information অনুযায়ী এটিই শক্তিশালী choice মনে হচ্ছে।"
            )

        return (
            "এই productগুলোর মধ্যে নির্ভরযোগ্য evidence যথেষ্ট নেই। "
            "তাই শুধু অনুমান করে কোনো একটাকে সেরা বলছি না। চাইলে price, stock বা available features দেখে optionগুলো তুলনা করে দিতে পারি।"
        )

    async def _search_products(self, store_id, message, filters, store_terms=None):
        attributes = getattr(filters, "attributes", {}) or {}
        query = self.db.query(Product).filter(Product.store_id == store_id)
        if filters:
            if filters.min_price is not None:
                query = query.filter(Product.price >= filters.min_price)
            if filters.max_price is not None:
                query = query.filter(Product.price <= filters.max_price)
            if filters.in_stock:
                query = query.filter(or_(Product.stock.is_(None), Product.stock > 0))
        if attributes:
            query = apply_attribute_filters(query, attributes, Product.attributes)
        groups = self._build_product_text_conditions(getattr(filters, "product_name", None)) if filters else []
        if groups:
            query = query.filter(and_(*groups))
        limit = 100 if is_recommendation_query(message) else 10
        results = query.order_by(Product.name.asc()).limit(limit).all()
        if is_recommendation_query(message):
            context = _RECOMMENDATION_CONTEXT.get()
            ranking_query = f"{message} {context}".strip()
            return self._rank(store_id, results, ranking_query)[:10]
        return results

    def _record_impressions(self, store_id: str, conversation_id: str, query: str, products: list[Product], interaction_id: str) -> None:
        if not products:
            return
        try:
            for product in products:
                record_event(
                    self.db,
                    store_id=store_id,
                    interaction_id=interaction_id,
                    event_type="impression",
                    product_id=str(product.id),
                    conversation_id=conversation_id,
                    query=query,
                )
        except Exception:
            self.db.rollback()
            logger.exception("Failed to record product impression events")

    async def handle(self, store_id: str, request):
        context_token = _RECOMMENDATION_CONTEXT.set("")
        behavior_token = _BEHAVIOR_SCORES.set({})
        try:
            message = getattr(request, "message", "").strip()
            conversation_id = getattr(request, "conversation_id", None)
            session = None
            context_products: list[Product] = []
            if conversation_id:
                session = self._get_or_create_session(store_id, conversation_id)
                history = self._load_history(session.id)
                previous_user = [m["content"] for m in history if m.get("role") == "user"][-3:]
                previous_context = self._load_product_context(session.id).get("query") or ""
                _RECOMMENDATION_CONTEXT.set(" ".join(previous_user + [previous_context]))
                context_products = self._context_products(store_id, session.id)

            if is_recommendation_query(message) and self._is_bare_recommendation(message) and not _RECOMMENDATION_CONTEXT.get().strip():
                if session is None:
                    conversation_id = conversation_id or __import__("uuid").uuid4().hex
                    session = self._get_or_create_session(store_id, conversation_id)
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = "কোন product/category-এর মধ্যে best জানতে চান? যেমন: laptop, phone, বা অন্য কোনো product।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                self._log_analytics_event(store_id=store_id, message=message, intent="recommendation", result_count=0)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

            # Resolve explicit references through the same canonical context resolver
            # used by ChatService. This preserves "2 নম্বরটার", "third one", etc.
            # instead of silently falling back to the first result.
            referenced_product = None
            if session is not None:
                referenced_product = self._get_referenced_product(store_id, session.id, message)

            if session is not None and referenced_product is not None and (self._is_link_request(message) or self._is_image_request(message)):
                product = referenced_product
                self._save_message(session_id=session.id, role="user", content=message)
                if self._is_image_request(message):
                    response_message = f"{self._format_product_name(product)}-এর image নিচে দেখানো হলো।" if getattr(product, "image_url", None) else f"দুঃখিত, {self._format_product_name(product)}-এর image এখন available নেই।"
                else:
                    response_message = f"অবশ্যই 😊 {self._format_product_name(product)}-এর product page-এর link নিচের card-এ দিলাম।" if getattr(product, "product_url", None) else f"দুঃখিত, {self._format_product_name(product)}-এর product link এখন available নেই।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": self._serialize_products([product]), "sources": []}

            if session is not None and referenced_product is not None and self._is_recommendation_explanation(message):
                self._save_message(session_id=session.id, role="user", content=message)
                context_candidates = self._context_products(store_id, session.id) or [referenced_product]
                response_message = self._recommendation_explanation(referenced_product, context_candidates)
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": self._serialize_products([referenced_product]), "sources": []}

            result = await super().handle(store_id=store_id, request=request)
            if not isinstance(result, dict):
                return result

            if is_recommendation_query(message) and result.get("products"):
                first = result["products"][0]
                product_objects = self._get_products_by_ids(store_id, [str(p.get("id")) for p in result["products"] if p.get("id")])
                has_evidence = self._recommendation_evidence(product_objects)
                if has_evidence:
                    best_line = f"আমার মতে {first.get('name', 'এই product')}-টাই এগিয়ে আছে"
                    if first.get("price") is not None:
                        best_line += f" — ৳{first['price']:,.0f}"
                    best_line += " 😊"
                else:
                    best_line = "এখনকার তথ্য অনুযায়ী নিশ্চিতভাবে কোনো একটাকে সেরা বলা যাচ্ছে না। নিচে available optionগুলো দিলাম—চাইলে price, stock বা অন্য details দেখে compare করে দিতে পারি।"
                result["message"] = best_line
                try:
                    target_session = self._get_or_create_session(store_id=store_id, conversation_id=result.get("conversation_id") or conversation_id)
                    latest = self.db.query(ChatMessage).filter(ChatMessage.session_id == target_session.id, ChatMessage.role == "assistant").order_by(ChatMessage.created_at.desc()).first()
                    if latest is not None:
                        latest.content = best_line
                        self.db.commit()
                except Exception:
                    self.db.rollback()
                    logger.exception("Failed to persist recommendation response")

            interaction_id = __import__("uuid").uuid4().hex
            products = result.get("products") or []
            ids = [str(p.get("id")) for p in products if p.get("id")]
            product_objects = self._get_products_by_ids(store_id, ids) if ids else []
            self._record_impressions(store_id=store_id, conversation_id=result.get("conversation_id") or conversation_id or "", query=message, products=product_objects, interaction_id=interaction_id)
            result["interaction_id"] = interaction_id
            return result
        finally:
            _BEHAVIOR_SCORES.reset(behavior_token)
            _RECOMMENDATION_CONTEXT.reset(context_token)

    def _get_next_products(self, store_id, query_text, filters_data, previous_ids, batch_size=5):
        query = self.db.query(Product).filter(Product.store_id == store_id)
        min_price = filters_data.get("min_price")
        max_price = filters_data.get("max_price")
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        if filters_data.get("in_stock", False):
            query = query.filter(or_(Product.stock.is_(None), Product.stock > 0))
        attributes = filters_data.get("attributes") or {}
        if isinstance(attributes, dict):
            query = apply_attribute_filters(query, attributes, Product.attributes)
        product_name = filters_data.get("product_name")
        if product_name:
            groups = self._build_product_text_conditions(product_name)
            if groups:
                query = query.filter(and_(*groups))
        if previous_ids:
            query = query.filter(~Product.id.in_(previous_ids))
        limit = max(batch_size, 100) if is_recommendation_query(query_text) else batch_size
        results = query.order_by(Product.name.asc()).limit(limit).all()
        if is_recommendation_query(query_text):
            ranked = self._rank(store_id, results, f"{query_text} {_RECOMMENDATION_CONTEXT.get()}".strip())
            return ranked[:batch_size]
        return results
