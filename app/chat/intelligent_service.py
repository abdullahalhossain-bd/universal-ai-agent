"""Conversation-intelligent commerce service.

This adapter keeps the existing ProfessionalCommerceChatService behavior while
adding deterministic product-reference resolution for follow-up turns.
"""
from __future__ import annotations

from app.chat.conversation_intelligence import resolve_follow_up
from app.chat.professional_service import ProfessionalCommerceChatService


class IntelligentCommerceChatService(ProfessionalCommerceChatService):
    """Professional commerce chat with deterministic conversation references."""

    def _get_referenced_product(self, store_id: str, session_id: str, message: str):
        context = self._load_product_context(session_id)
        product_ids = [str(value) for value in (context.get("product_ids") or [])]
        if not product_ids:
            return None

        resolution = resolve_follow_up(message, product_ids)
        if not resolution.is_follow_up:
            return super()._get_referenced_product(
                store_id=store_id,
                session_id=session_id,
                message=message,
            )

        if resolution.product_ids:
            products = self._get_products_by_ids(
                store_id=store_id,
                product_ids=list(resolution.product_ids),
            )
            if resolution.product_index is not None:
                return products[0] if products else None
            # A multi-product action such as compare is handled by the
            # caller; returning None prevents accidental first-product guesses.
            return None

        return None

    async def handle(self, store_id: str, request):
        message = getattr(request, "message", "").strip()
        conversation_id = getattr(request, "conversation_id", None)

        if conversation_id:
            session = self._get_or_create_session(store_id, conversation_id)
            context = self._load_product_context(session.id)
            product_ids = [str(value) for value in (context.get("product_ids") or [])]
            resolution = resolve_follow_up(message, product_ids)

            if resolution.action == "compare_products" and resolution.product_ids:
                products = self._get_products_by_ids(
                    store_id=store_id,
                    product_ids=list(resolution.product_ids),
                )
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = self._context_comparison_message(products)
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": self._enrich_product_payload(
                        store_id,
                        self.db,
                        self._serialize_products(products),
                    ),
                    "sources": [],
                }

        return await super().handle(store_id=store_id, request=request)
