"""Data-driven conversation intelligence for commerce chat.

The resolver never contains merchant product/category names. It derives references
from the products and conversation contexts actually stored for the current store.
"""
from __future__ import annotations

import re

from sqlalchemy import or_

from app.chat.conversation_intelligence import resolve_follow_up
from app.chat.models import ChatMessage
from app.chat.professional_service import ProfessionalCommerceChatService
from app.db.models import Product


class IntelligentCommerceChatService(ProfessionalCommerceChatService):
    """Professional commerce chat with dynamic, catalog-backed references."""

    _MAX_CONTEXT_TURNS = 5
    _MAX_CONTEXT_PRODUCTS = 30

    @staticmethod
    def _is_ambiguous_deictic(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.casefold().strip())
        # These are grammatical references, not merchant-specific entities.
        return bool(re.search(r"(?:^|\s)(eta|etar|ota|otar|oi|it|this|that)(?:\s|$)", normalized)) or bool(
            re.search(r"(?:^|\s)(এটা|এটার|ওটা|ওটার|ওই|ওইটা|সেটা|সেটার|এইটা|এইটার)(?:\s|$)", normalized)
        )

    def _load_recent_context_product_ids(self, session_id: str) -> list[str]:
        """Collect product references from several recent search contexts.

        The current product context remains the first source, while older contexts
        are retained as a fallback. This makes follow-ups multi-turn without making
        the application depend on a fixed product/category vocabulary.
        """
        rows = (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "product_context",
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(self._MAX_CONTEXT_TURNS)
            .all()
        )
        ids: list[str] = []
        seen: set[str] = set()
        import json

        for row in rows:
            try:
                payload = json.loads(row.content or "{}")
            except (TypeError, ValueError):
                continue
            for value in payload.get("product_ids") or []:
                value = str(value)
                if value and value not in seen:
                    seen.add(value)
                    ids.append(value)
                if len(ids) >= self._MAX_CONTEXT_PRODUCTS:
                    return ids
        return ids

    def _dynamic_reference_products(self, store_id: str, session_id: str, message: str) -> list[Product]:
        """Resolve named references from actual catalog/context data.

        Examples such as "HP ta", "black one", or a SKU are not hardcoded here.
        The service searches the current store's previously surfaced products using
        their real name/brand/category/description/SKU fields.
        """
        context_ids = self._load_recent_context_product_ids(session_id)
        if not context_ids:
            return []

        candidates = self._get_products_by_ids(store_id, context_ids)
        normalized = re.sub(r"\s+", " ", message.casefold().strip())
        if not normalized:
            return []

        # Let the deterministic ordinal/deictic resolver handle pure references.
        structured = resolve_follow_up(normalized, [{"id": str(p.id)} for p in candidates])
        if structured.product_ids:
            by_id = {str(p.id): p for p in candidates}
            return [by_id[pid] for pid in structured.product_ids if pid in by_id]

        # For a named reference, score catalog fields by token coverage. No fixed
        # merchant names, categories, colors, brands, etc. are embedded in code.
        stop = {
            "the", "this", "that", "one", "product", "please", "show", "give",
            "dao", "den", "dাও", "দাও", "দেন", "দেখাও", "দেখান", "এর", "র", "টা", "টি", "তার", "ওই", "এটা",
        }
        tokens = [
            token for token in re.findall(r"[\w\u0980-\u09ff]+", normalized)
            if len(token) >= 2 and token not in stop and not token.isdigit()
        ]
        if not tokens:
            return []

        scored: list[tuple[int, Product]] = []
        for product in candidates:
            fields = [
                getattr(product, "name", None),
                getattr(product, "brand", None),
                getattr(product, "category", None),
                getattr(product, "sku", None),
                getattr(product, "description", None),
            ]
            haystack = " ".join(str(value or "").casefold() for value in fields)
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, product))

        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return []
        best_score = scored[0][0]
        best = [product for score, product in scored if score == best_score]
        return best if len(best) == 1 else []

    def _get_referenced_product(self, store_id: str, session_id: str, message: str):
        candidates = self._dynamic_reference_products(store_id, session_id, message)
        if len(candidates) == 1:
            return candidates[0]

        context_ids = self._load_recent_context_product_ids(session_id)
        if not context_ids:
            return None

        resolution = resolve_follow_up(message, [{"id": pid} for pid in context_ids])
        if resolution.product_ids:
            products = self._get_products_by_ids(store_id, list(resolution.product_ids))
            return products[0] if len(products) == 1 else None

        # Never guess the first product for an ambiguous pronoun.
        if len(context_ids) > 1 and self._is_ambiguous_deictic(message):
            return None
        return super()._get_referenced_product(store_id=store_id, session_id=session_id, message=message)

    async def handle(self, store_id: str, request):
        message = getattr(request, "message", "").strip()
        conversation_id = getattr(request, "conversation_id", None)

        if conversation_id:
            session = self._get_or_create_session(store_id, conversation_id)
            context_ids = self._load_recent_context_product_ids(session.id)
            resolution = resolve_follow_up(message, [{"id": pid} for pid in context_ids])

            if resolution.action == "compare_products" and resolution.product_ids:
                products = self._get_products_by_ids(store_id, list(resolution.product_ids))
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = self._context_comparison_message(products)
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": self._enrich_product_payload(store_id, self.db, self._serialize_products(products)),
                    "sources": [],
                }

            # Dynamic named references such as a merchant's real brand/product/SKU
            # are resolved from context before falling through to normal search.
            if self._dynamic_reference_products(store_id, session.id, message):
                referenced = self._get_referenced_product(store_id, session.id, message)
                if referenced is not None and (
                    self._is_link_request(message)
                    or self._is_image_request(message)
                    or self._is_recommendation_explanation(message)
                ):
                    return await super().handle(store_id=store_id, request=request)

            if len(context_ids) > 1 and not resolution.product_ids and self._is_ambiguous_deictic(message):
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = "কোন product-এর কথা বলছেন? আগের list-এর নম্বর বা product-এর নাম বলুন—আমি ঠিক সেটার তথ্য দেব।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": [],
                    "sources": [],
                }

        return await super().handle(store_id=store_id, request=request)
