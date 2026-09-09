"""Data-driven conversation intelligence for commerce chat.

The resolver never contains merchant product/category names. It derives references
from the products, merchant schema and conversation state actually stored for the
current store.
"""
from __future__ import annotations

import json
import re

from app.chat.conversation_intelligence import resolve_follow_up
from app.chat.models import ChatMessage
from app.chat.professional_service import ProfessionalCommerceChatService
from app.db.models import Product
from app.planner.rule_planner import plan
from app.search.store_vocabulary import get_store_vocabulary


class IntelligentCommerceChatService(ProfessionalCommerceChatService):
    """Professional commerce chat with dynamic, catalog-backed references."""

    _MAX_CONTEXT_TURNS = 5
    _MAX_CONTEXT_PRODUCTS = 30

    @staticmethod
    def _is_ambiguous_deictic(message: str) -> bool:
        normalized = re.sub(r"\s+", " ", message.casefold().strip())
        return bool(re.search(r"(?:^|\s)(eta|etar|ota|otar|oi|it|this|that)(?:\s|$)", normalized)) or bool(
            re.search(r"(?:^|\s)(এটা|এটার|ওটা|ওটার|ওই|ওইটা|সেটা|সেটার|এইটা|এইটার)(?:\s|$)", normalized)
        )

    def _load_recent_context_product_ids(self, session_id: str) -> list[str]:
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "product_context")
            .order_by(ChatMessage.created_at.desc())
            .limit(self._MAX_CONTEXT_TURNS)
            .all()
        )
        ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            try:
                payload = json.loads(row.content or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
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
        context_ids = self._load_recent_context_product_ids(session_id)
        if not context_ids:
            return []
        candidates = self._get_products_by_ids(store_id, context_ids)
        normalized = re.sub(r"\s+", " ", message.casefold().strip())
        if not normalized:
            return []
        structured = resolve_follow_up(normalized, [{"id": str(p.id)} for p in candidates])
        if structured.product_ids:
            by_id = {str(p.id): p for p in candidates}
            return [by_id[pid] for pid in structured.product_ids if pid in by_id]

        # Named references are matched against actual catalog fields. Nothing
        # here assumes a merchant-specific brand, category, color or product.
        stop = {
            "the", "this", "that", "one", "product", "please", "show", "give",
            "dao", "den", "দাও", "দেন", "দেখাও", "দেখান", "এর", "র", "টা", "টি", "তার", "ওই", "এটা",
        }
        tokens = [
            token for token in re.findall(r"[\w\u0980-\u09ff]+", normalized)
            if len(token) >= 2 and token not in stop and not token.isdigit()
        ]
        if not tokens:
            return []
        scored: list[tuple[int, Product]] = []
        for product in candidates:
            fields = [getattr(product, "name", None), getattr(product, "category", None), getattr(product, "description", None)]
            attributes = getattr(product, "attributes", None) or {}
            fields.extend([str(k) for k in attributes.keys()])
            fields.extend([str(v) for v in attributes.values() if isinstance(v, (str, int, float, bool))])
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
        if len(context_ids) > 1 and self._is_ambiguous_deictic(message):
            return None
        return super()._get_referenced_product(store_id=store_id, session_id=session_id, message=message)

    @staticmethod
    def _merge_filters(previous: dict, current) -> dict:
        """Merge a new turn into the active query state.

        The current turn wins for dimensions it explicitly changes. Other
        constraints survive, so "under 80k" -> "black" -> "8GB" becomes one
        cumulative query. The merge is schema-neutral because attributes are
        keyed by the merchant-declared schema rather than a global attribute list.
        """
        previous = previous if isinstance(previous, dict) else {}
        merged = {
            "min_price": previous.get("min_price"),
            "max_price": previous.get("max_price"),
            "in_stock": bool(previous.get("in_stock", False)),
            "product_name": previous.get("product_name"),
            "recommendation": bool(previous.get("recommendation", False)),
            "attributes": dict(previous.get("attributes") or {}),
        }
        if current is None:
            return merged
        current_attrs = dict(getattr(current, "attributes", {}) or {})
        if current_attrs:
            merged["attributes"].update(current_attrs)
        if getattr(current, "min_price", None) is not None:
            merged["min_price"] = current.min_price
        if getattr(current, "max_price", None) is not None:
            merged["max_price"] = current.max_price
        if getattr(current, "product_name", None):
            merged["product_name"] = current.product_name
        if getattr(current, "in_stock", False):
            merged["in_stock"] = True
        if getattr(current, "recommendation", False):
            merged["recommendation"] = True
        return merged

    @staticmethod
    def _effective_query(state: dict, current_message: str, schema: dict) -> str:
        """Build a schema-aware query from retained state + the new turn."""
        parts: list[str] = []
        product_name = state.get("product_name")
        if product_name:
            parts.append(str(product_name))
        min_price = state.get("min_price")
        max_price = state.get("max_price")
        if min_price is not None:
            parts.append(f"above {min_price:g}")
        if max_price is not None:
            parts.append(f"under {max_price:g}")
        for key, value in (state.get("attributes") or {}).items():
            aliases = schema.get(str(key).casefold(), []) if isinstance(schema, dict) else []
            label = aliases[0] if aliases else key
            parts.append(f"{label} {value}")
        if state.get("in_stock"):
            parts.append("in stock")
        parts.append(current_message)
        return " ".join(str(part) for part in parts if str(part).strip())

    def _prepare_stateful_query(self, store_id: str, session_id: str, message: str) -> tuple[str, dict] | None:
        context = self._load_product_context(session_id)
        previous_filters = context.get("filters") or {}
        if not previous_filters:
            return None
        try:
            store_terms = __import__("asyncio").run(get_store_vocabulary(self.db, store_id))
        except RuntimeError:
            # The request already runs inside an event loop; fetch the vocabulary
            # asynchronously in handle() instead of blocking here.
            return None
        except Exception:
            return None
        action = plan(message, store_terms)
        current = getattr(action, "product_filters", None)
        merged = self._merge_filters(previous_filters, current)
        if merged == {
            "min_price": previous_filters.get("min_price"),
            "max_price": previous_filters.get("max_price"),
            "in_stock": bool(previous_filters.get("in_stock", False)),
            "product_name": previous_filters.get("product_name"),
            "recommendation": bool(previous_filters.get("recommendation", False)),
            "attributes": dict(previous_filters.get("attributes") or {}),
        }:
            return None
        return self._effective_query(merged, message, getattr(store_terms, "attribute_schema", {}) or {}), merged

    async def handle(self, store_id: str, request):
        message = getattr(request, "message", "").strip()
        conversation_id = getattr(request, "conversation_id", None)
        original_message = message
        original_conversation_id = conversation_id

        if conversation_id:
            session = self._get_or_create_session(store_id, conversation_id)
            context_ids = self._load_recent_context_product_ids(session.id)
            resolution = resolve_follow_up(message, [{"id": pid} for pid in context_ids])

            if resolution.action == "compare_products" and resolution.product_ids:
                products = self._get_products_by_ids(store_id, list(resolution.product_ids))
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = self._context_comparison_message(products)
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": self._enrich_product_payload(store_id, self.db, self._serialize_products(products)), "sources": []}

            if self._dynamic_reference_products(store_id, session.id, message):
                referenced = self._get_referenced_product(store_id, session.id, message)
                if referenced is not None and (self._is_link_request(message) or self._is_image_request(message) or self._is_recommendation_explanation(message)):
                    return await super().handle(store_id=store_id, request=request)

            if len(context_ids) > 1 and not resolution.product_ids and self._is_ambiguous_deictic(message):
                self._save_message(session_id=session.id, role="user", content=message)
                response_message = "কোন product-এর কথা বলছেন? আগের list-এর নম্বর বা product-এর নাম বলুন—আমি ঠিক সেটার তথ্য দেব।"
                self._save_message(session_id=session.id, role="assistant", content=response_message)
                return {"conversation_id": conversation_id, "type": "product_search", "message": response_message, "products": [], "sources": []}

            # Stateful query carry-over: retrieve the merchant's declared schema,
            # parse only the new turn, merge explicit changes into the prior state,
            # then let the normal planner/search pipeline execute the merged query.
            context = self._load_product_context(session.id)
            previous_filters = context.get("filters") or {}
            if previous_filters:
                try:
                    store_terms = await get_store_vocabulary(self.db, store_id)
                    action = plan(message, store_terms)
                    current = getattr(action, "product_filters", None)
                    merged = self._merge_filters(previous_filters, current)
                    changed = merged != {
                        "min_price": previous_filters.get("min_price"),
                        "max_price": previous_filters.get("max_price"),
                        "in_stock": bool(previous_filters.get("in_stock", False)),
                        "product_name": previous_filters.get("product_name"),
                        "recommendation": bool(previous_filters.get("recommendation", False)),
                        "attributes": dict(previous_filters.get("attributes") or {}),
                    }
                    if changed and current is not None:
                        request.message = self._effective_query(merged, message, getattr(store_terms, "attribute_schema", {}) or {})
                except Exception:
                    request.message = original_message

        result = await super().handle(store_id=store_id, request=request)
        request.message = original_message
        request.conversation_id = original_conversation_id

        # Keep analytics/user-visible query natural while retaining the merged
        # structured state saved by the underlying product-context mechanism.
        if conversation_id:
            session = self._get_or_create_session(store_id, conversation_id)
            latest_context = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id,
                ChatMessage.role == "product_context",
            ).order_by(ChatMessage.created_at.desc()).first()
            if latest_context is not None:
                try:
                    payload = json.loads(latest_context.content or "{}")
                    payload["query"] = original_message
                    latest_context.content = json.dumps(payload, ensure_ascii=False)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
        return result
