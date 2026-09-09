"""ChatService variant with first-class merchant-defined attributes and recommendations."""
from __future__ import annotations

from contextvars import ContextVar

from sqlalchemy import and_, or_

from app.chat.service import ChatService
from app.db.models import Product
from app.products.attribute_filters import apply_attribute_filters
from app.products.recommendation import is_recommendation_query, rank_products
from app.search.stopwords import STOPWORDS
from app.search.synonyms import expand_terms

_RECOMMENDATION_CONTEXT: ContextVar[str] = ContextVar("recommendation_context", default="")


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
                "attributes": getattr(filters, "attributes", {}) or {},
            }
        super()._save_product_context(session_id=session_id, products=products, query=query, filters=filters, offset=offset)

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

        # Fetch a wider candidate pool, then rank only after all hard filters.
        limit = 50 if is_recommendation_query(message) else 10
        results = query.order_by(Product.name.asc()).limit(limit).all()
        if is_recommendation_query(message):
            context = _RECOMMENDATION_CONTEXT.get()
            ranking_query = f"{message} {context}".strip()
            return rank_products(results, ranking_query)[:10]
        return results

    async def handle(self, store_id: str, request):
        """Carry recent conversation intent into an otherwise ambiguous 'best' query."""
        token = _RECOMMENDATION_CONTEXT.set("")
        try:
            conversation_id = getattr(request, "conversation_id", None)
            if conversation_id:
                session = self._get_or_create_session(store_id, conversation_id)
                history = self._load_history(session.id)
                previous_user = [m["content"] for m in history if m.get("role") == "user"][-2:]
                previous_context = self._load_product_context(session.id).get("query") or ""
                _RECOMMENDATION_CONTEXT.set(" ".join(previous_user + [previous_context]))
            return await super().handle(store_id=store_id, request=request)
        finally:
            _RECOMMENDATION_CONTEXT.reset(token)

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

        results = query.order_by(Product.name.asc()).limit(batch_size).all()
        if is_recommendation_query(query_text):
            return rank_products(results, f"{query_text} {_RECOMMENDATION_CONTEXT.get()}".strip())
        return results
