"""ChatService variant with first-class merchant-defined attribute filtering."""
from __future__ import annotations

from sqlalchemy import and_, or_

from app.chat.service import ChatService
from app.db.models import Product
from app.products.attribute_filters import apply_attribute_filters
from app.search.stopwords import STOPWORDS
from app.search.synonyms import expand_terms


class DynamicAttributeChatService(ChatService):
    """Use Product.attributes as structured filters without changing ChatService's state machine."""

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
            groups.append(
                or_(
                    *[
                        or_(
                            Product.name.ilike(f"%{synonym}%"),
                            Product.description.ilike(f"%{synonym}%"),
                            Product.category.ilike(f"%{synonym}%"),
                        )
                        for synonym in synonyms
                    ]
                )
            )
        return groups

    async def _search_products(self, store_id, message, filters, store_terms=None):
        attributes = getattr(filters, "attributes", {}) or {}
        if not attributes:
            return await super()._search_products(
                store_id=store_id,
                message=message,
                filters=filters,
                store_terms=store_terms,
            )

        query = self.db.query(Product).filter(Product.store_id == store_id)

        if filters.min_price is not None:
            query = query.filter(Product.price >= filters.min_price)
        if filters.max_price is not None:
            query = query.filter(Product.price <= filters.max_price)
        if filters.in_stock:
            query = query.filter(or_(Product.stock.is_(None), Product.stock > 0))

        # Every requested merchant-defined attribute is an AND predicate.
        query = apply_attribute_filters(query, attributes, Product.attributes)

        # Product/category terms remain normal text search and are AND-ed
        # with the structured attribute predicates.
        groups = self._build_product_text_conditions(filters.product_name)
        if groups:
            query = query.filter(and_(*groups))

        results = query.order_by(Product.name.asc()).limit(10).all()

        # Attribute constraints are authoritative. Do not fall back to a
        # broader text-only query because that could violate the customer's
        # requested attributes.
        return results

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
        groups = self._build_product_text_conditions(product_name or query_text)
        if groups:
            query = query.filter(and_(*groups))

        if previous_ids:
            query = query.filter(~Product.id.in_(previous_ids))

        return query.order_by(Product.name.asc()).limit(batch_size).all()
