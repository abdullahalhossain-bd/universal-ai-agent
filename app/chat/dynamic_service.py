"""ChatService variant with first-class merchant-defined attributes and recommendations."""
from __future__ import annotations

from contextvars import ContextVar
import json
import logging
import re
import uuid

from sqlalchemy import and_, or_

from app.chat.service import ChatService
from app.chat.models import ChatMessage
from app.chat.intent_semantics import classify_product_link_request, parse_llm_link_intent
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
    """ChatService with structured attributes, recommendations and stateful follow-ups."""

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

    def _set_pending_action(self, session_id: str, action: str, product_ids: list[str] | None = None) -> None:
        """Persist one structured next-step action; no confirmation phrases are stored."""
        context_message = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "product_context")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if context_message is None:
            return
        try:
            context = json.loads(context_message.content or "{}")
            context["pending_action"] = {
                "action": action,
                "product_ids": product_ids or context.get("product_ids") or [],
                "turns_left": 1,
            }
            context_message.content = json.dumps(context, ensure_ascii=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Failed to persist pending conversational action")

    def _load_pending_action(self, session_id: str) -> dict | None:
        context = self._load_product_context(session_id)
        action = context.get("pending_action")
        if not isinstance(action, dict) or not action.get("action"):
            return None
        try:
            if int(action.get("turns_left", 0)) < 1:
                return None
        except (TypeError, ValueError):
            return None
        return action

    def _consume_pending_action(self, session_id: str) -> None:
        context_message = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "product_context")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if context_message is None:
            return
        try:
            context = json.loads(context_message.content or "{}")
            context.pop("pending_action", None)
            context_message.content = json.dumps(context, ensure_ascii=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Failed to consume pending conversational action")

    def _message_has_product_match(self, store_id: str, message: str) -> bool:
        """Check whether the new turn independently identifies catalog content.

        This is deliberately data-driven: it does not maintain a list of
        confirmation words or Bengali/Banglish variants. If the new turn can
        actually match this merchant's catalog, it remains a fresh query.
        """
        tokens = [
            token.strip(".,!?;:()[]{}\"'")
            for token in re.split(r"\s+", message.casefold())
            if len(token.strip(".,!?;:()[]{}\"'")) >= 3
        ]
        if not tokens:
            return False
        generic = {"the", "this", "that", "please", "show", "give", "want", "need", "dao", "den", "দাও", "দেন", "দেখাও", "দেখান"}
        tokens = [token for token in tokens if token not in generic]
        if not tokens:
            return False
        query = self.db.query(Product.id).filter(Product.store_id == store_id)
        conditions = []
        for token in tokens[:8]:
            conditions.append(or_(
                Product.name.ilike(f"%{token}%"),
                Product.category.ilike(f"%{token}%"),
                Product.brand.ilike(f"%{token}%"),
                Product.description.ilike(f"%{token}%"),
            ))
        return query.filter(or_(*conditions)).first() is not None

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
        generic = {"best", "top", "recommend", "recommended", "suggest", "suggestion", "konta", "kon", "ta", "one", "which", "is", "the", "please", "কোনটা", "কোনটি", "কোন", "টা", "টি", "সেরা", "ভালো", "ভাল", "সর্বোত্তম"}
        return all(token in generic for token in tokens) and any(token in {"best", "top", "recommend", "recommended", "suggest", "suggestion", "সেরা", "ভালো", "ভাল", "সর্বোত্তম"} for token in tokens)

    @staticmethod
    def _is_link_request(message: str) -> bool:
        """Fast, deterministic link detection for explicit page/link wording."""
        return classify_product_link_request(message) is True

    async def _detect_product_link_request(self, message: str, has_product_context: bool) -> bool:
        """Use local semantic composition first; call the LLM only on ambiguity."""
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
            logger.debug("Semantic link-intent fallback failed", exc_info=True)
            return False

    @staticmethod
    def _is_image_request(message: str) -> bool:
        q = message.casefold().strip()
        return any(term in q for term in ("image", "photo", "picture", "pic", "ছবি", "ইমেজ", "ফটো"))

    @staticmethod
    def _is_recommendation_explanation(message: str) -> bool:
        q = message.casefold().strip()
        patterns = ("kemne sera", "kemon kore sera", "ken sera", "karon ki", "why best", "how best", "how is it best", "why is it best", "best keno", "কেন সেরা", "কিভাবে সেরা", "কীভাবে সেরা", "কেন best", "কীভাবে best", "কেন ভালো", "কিভাবে ভালো", "basis ki", "basis", "reason")
        return any(pattern in q for pattern in patterns)

    def _context_products(self, store_id: str, session_id: str, product_ids: list[str] | None = None) -> list[Product]:
        context_ids = product_ids
        if context_ids is None:
            context_ids = self._load_product_context(session_id).get("product_ids") or []
        return self._get_products_by_ids(store_id, context_ids)

    @staticmethod
    def _recommendation_evidence(products: list[Product]) -> bool:
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
        rating, reviews, sales, bestseller = (getattr(product, key, None) for key in ("rating", "review_count", "sales_count", "bestseller_score"))
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
            return f"{self._format_product_name(product)}-কে আমি এগিয়ে রাখছি কারণ " + ", ".join(reasons) + ". তাই available information অনুযায়ী এটিই শক্তিশালী choice মনে হচ্ছে।"
        return "এই productগুলোর মধ্যে নির্ভরযোগ্য evidence যথেষ্ট নেই। তাই শুধু অনুমান করে কোনো একটাকে সেরা বলছি না। চাইলে price, stock বা available features দেখে optionগুলো তুলনা করে দিতে পারি।"

    def _context_comparison_message(self, products: list[Product]) -> str:
        if not products:
            return "দুঃখিত, আগের product optionগুলো এখন আর পাওয়া যাচ্ছে না। নতুন করে product লিখে খুঁজে দিতে পারি।"
        lines = ["অবশ্যই 😊 আগের product optionগুলো price ও stock অনুযায়ী তুলনা করে দিলাম:"]
        for product in products:
            price = getattr(product, "price", None)
            stock = getattr(product, "stock", None)
            price_text = f"৳{float(price):,.0f}" if price is not None else "দাম জানা নেই"
            stock_text = "স্টকে আছে" if stock is None or float(stock) > 0 else "স্টক শেষ"
            lines.append(f"• {self._format_product_name(product)} — {price_text} — {stock_text}")
        lines.append("চাইলে budget বা specific feature ধরে এগুলো আরও narrow করে দিতে পারি।")
        return "\n".join(lines)

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
            ranking_query = f"{message} {_RECOMMENDATION_CONTEXT.get()}".strip()
            return self._rank(store_id, results, ranking_query)[:10]
        return results

    def _record_impressions(self, store_id: str, conversation_id: str, query: str, products: list[Product], interaction_id: str) -> None:
        if not products:
            return
        try:
            for product in products:
                record_event(self.db, store_id=store_id, interaction_id=interaction_id, event_type="impression", product_id=str(product.id), conversation_id=conversation_id, query=query)
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
            pending_action = None
            if conversation_id:
                session = self._get_or_create_session(store_id, conversation_id)
                history = self._load_history(session.id)
                previous_user = [m["content"] for m in history if m.get("role") == "user"][-3:]
                previous_context = self._load_product_context(session.id).get("query") or ""
                _RECOMMENDATION_CONTEXT.set(" ".join(previous_user + [previous_context]))
                context_products = self._context_products(store_id, session.id)
                pending_action = self._load_pending_action(session.id)

            if is_recommendation_query(message) and self._is_bare_recommendation(message) and not _RECOMMENDATION_CONTEXT.get().strip():
                if session is None:
                    conversation_id = conversation_id or uuid.uuid4().hex
                    session = self._get_or_create_session(store_id, conversation_id)
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = "কোন product/category-এর মধ্যে best জানতে চান? যেমন: laptop, phone, বা অন্য কোনো product।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                self._log_analytics_event(store_id=store_id, message=message, intent="recommendation", result_count=0)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

            # Resolve the special product-link intent once for this turn. Explicit
            # wording is handled locally; only ambiguous language with product
            # context reaches the LLM fallback.
            is_link = await self._detect_product_link_request(message, bool(context_products or session and self._load_product_context(session.id).get("product_ids")))

            # Conversation continuation is state-driven, not phrase-driven.
            if session is not None and pending_action and context_products:
                explicit_reference = self._get_referenced_product(store_id, session.id, message)
                is_special_request = is_link or self._is_image_request(message) or self._is_recommendation_explanation(message) or is_recommendation_query(message)
                has_new_product = self._message_has_product_match(store_id, message)
                if explicit_reference is None and not is_special_request and not has_new_product:
                    action = pending_action.get("action")
                    if action == "compare_products":
                        self._save_message(session_id=session.id, role="user", content=message)
                        response_message = self._context_comparison_message(context_products)
                        self._save_message(session_id=session.id, role="assistant", content=response_message)
                        self._consume_pending_action(session.id)
                        interaction_id = uuid.uuid4().hex
                        self._record_impressions(store_id=store_id, conversation_id=conversation_id or "", query=message, products=context_products, interaction_id=interaction_id)
                        return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": self._serialize_products(context_products), "sources": [], "interaction_id": interaction_id}

            referenced_product = None
            if session is not None:
                referenced_product = self._get_referenced_product(store_id, session.id, message)

            if session is not None and referenced_product is not None and (is_link or self._is_image_request(message)):
                self._save_message(session_id=session.id, role="user", content=message)
                product = referenced_product
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
                    if not has_evidence:
                        self._set_pending_action(target_session.id, "compare_products", [str(p.id) for p in product_objects])
                except Exception:
                    self.db.rollback()
                    logger.exception("Failed to persist recommendation response/action")

            interaction_id = uuid.uuid4().hex
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
        return query.order_by(Product.name.asc()).limit(batch_size).all()
