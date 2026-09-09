"""Conversation-intelligent commerce service.

This adapter keeps the existing ProfessionalCommerceChatService behavior while
adding deterministic product-reference resolution for follow-up turns.
"""
from __future__ import annotations

import re

from app.chat.conversation_intelligence import resolve_follow_up
from app.chat.professional_service import ProfessionalCommerceChatService


class IntelligentCommerceChatService(ProfessionalCommerceChatService):
    """Professional commerce chat with deterministic conversation references."""

    @staticmethod
    def _is_ambiguous_deictic(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.casefold().strip())
        tokens = set(normalized.split())
        return bool(tokens & {
            "eta", "etar", "ota", "otar", "oi", "it", "this", "that",
            "this one", "that one", "এটা", "এটার", "ওটা", "ওটার", "ওই",
            "ওইটা", "সেটা", "সেটার", "এইটা", "এইটার",
        })

    def _get_referenced_product(self, store_id: str, session_id: str, message: str):
        context = self._load_product_context(session_id)
        product_ids = [str(value) for value in (context.get("product_ids") or [])]
        if not product_ids:
            return None

        resolution = resolve_follow_up(message, product_ids)
        if not resolution.is_follow_up:
            # The resolver intentionally treats a bare ambiguous deictic as
            # unresolved. Do not fall back to the legacy "first product"
            # behavior when several products are in context.
            if len(product_ids) > 1 and self._is_ambiguous_deictic(message):
                return None
            return super()._get_referenced_product(
                store_id=store_id,
                session_id=session_id,
                message=message,
            )

        # An ambiguous reference such as "eta dam koto" with several products
        # deliberately returns no product instead of guessing product #1.
        if not resolution.product_ids:
            return None

        products = self._get_products_by_ids(
            store_id=store_id,
            product_ids=list(resolution.product_ids),
        )
        return products[0] if len(products) == 1 else None

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

            if len(product_ids) > 1 and not resolution.product_ids and self._is_ambiguous_deictic(message):
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = "কোন product-এর কথা বলছেন? তালিকার নম্বর বা product-এর নাম বলুন—আমি ঠিক সেটার তথ্য দেব।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": [],
                    "sources": [],
                }

        return await super().handle(store_id=store_id, request=request)
