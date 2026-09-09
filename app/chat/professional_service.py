"""Professional commerce conversation layer on top of the dynamic chat service."""
from __future__ import annotations

import uuid

from app.chat.dynamic_service import DynamicAttributeChatService


class ProfessionalCommerceChatService(DynamicAttributeChatService):
    """Keep recommendation follow-ups grounded in actual product context."""

    async def handle(self, store_id: str, request):
        message = getattr(request, "message", "").strip()
        conversation_id = getattr(request, "conversation_id", None)

        # A bare recommendation such as "best konta?" is meaningful only
        # when the conversation already has a persisted product result.
        # Looking at chat history alone is unsafe because greetings or
        # unrelated questions would make the request look contextual.
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
                self._log_analytics_event(
                    store_id=store_id,
                    message=message,
                    intent="recommendation",
                    result_count=0,
                )
                return {
                    "conversation_id": conversation_id,
                    "type": "product_search",
                    "message": response_message,
                    "products": [],
                    "sources": [],
                }

        # No conversation ID means there is no prior product context. Let
        # the dynamic service create the conversation and apply its normal
        # bare-recommendation guard.
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
            self._log_analytics_event(
                store_id=store_id,
                message=message,
                intent="recommendation",
                result_count=0,
            )
            return {
                "conversation_id": conversation_id,
                "type": "product_search",
                "message": response_message,
                "products": [],
                "sources": [],
            }

        return await super().handle(store_id=store_id, request=request)
