"""
VisionService — budget-aware, cache-aware entry point for image
analysis. Mirrors the text LLM path in `app.chat.service.ChatService`
(same reserve/finalize/fail budget-reservation pattern via
`UsageRepository`) but for the vision model.

Call order:
    1. Cache lookup (VisionCache, keyed on image_hash + task) —
       skipped silently if no cache backend is available.
    2. Preflight cost estimate + atomic budget reservation.
    3. Read image bytes from object storage.
    4. VisionRouter provider call.
    5. Finalize/fail the reservation based on the outcome, cache the
       result on success.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.ai.cost_engine import estimate_cost


class VisionBudgetExceededError(RuntimeError):
    """
    The store's monthly AI usage budget has no room left for this
    vision request. Callers should surface a friendly "limit
    reached" message rather than attempting the provider call.
    """


class VisionService:

    def __init__(self, db: Session, usage_repo=None):

        self.db = db

        if usage_repo is not None:
            self.usage_repo = usage_repo
        else:
            from app.usage.repository import UsageRepository

            self.usage_repo = UsageRepository(db)

    async def analyze(
        self,
        *,
        store,
        image_record,
        task: str,
        question: str | None = None,
    ) -> dict:

        cache = self._get_cache()
        cache_key_task = f"{task}:{question or ''}"

        if cache is not None and image_record.image_hash:

            cached = await self._cache_get(
                cache, image_record.image_hash, cache_key_task
            )

            if cached is not None:
                return cached

        # ---------------------------------
        # Preflight cost estimate + reservation
        # ---------------------------------

        import uuid

        estimated_input_tokens = settings.vision_image_token_estimate
        max_output_tokens = 400

        preflight_cost = estimate_cost(
            input_tokens=estimated_input_tokens,
            output_tokens=max_output_tokens,
            input_price=settings.groq_vision_input_cost_per_1m,
            output_price=settings.groq_vision_output_cost_per_1m,
        )

        request_id = str(uuid.uuid4())

        reservation = self.usage_repo.reserve_budget(
            store_id=store.id,
            conversation_id=(image_record.conversation_id or request_id),
            request_id=request_id,
            route="groq_vision",
            model=settings.groq_vision_model,
            estimated_cost=preflight_cost,
        )

        if reservation is None:
            raise VisionBudgetExceededError(
                f"Monthly AI usage budget exceeded for store {store.id}"
            )

        # ---------------------------------
        # Provider call
        # ---------------------------------

        from app.images.storage import get_object_storage
        from app.vision.vision_router import VisionRouter

        try:
            storage = get_object_storage()
            image_bytes = await storage.read(image_record.storage_key)

            analysis = await VisionRouter().analyze(
                image_bytes=image_bytes,
                mime_type=image_record.mime_type,
                task=task,
                question=question,
            )

        except Exception:
            self.usage_repo.fail_budget_reservation(request_id=request_id)
            raise

        # ---------------------------------
        # Finalize reservation with actual usage
        # ---------------------------------

        actual_input_tokens = estimated_input_tokens
        actual_output_tokens = max_output_tokens

        actual_cost = estimate_cost(
            input_tokens=actual_input_tokens,
            output_tokens=actual_output_tokens,
            input_price=settings.groq_vision_input_cost_per_1m,
            output_price=settings.groq_vision_output_cost_per_1m,
        )

        self.usage_repo.finalize_budget_reservation(
            request_id=request_id,
            input_tokens=actual_input_tokens,
            output_tokens=actual_output_tokens,
            actual_cost=actual_cost,
            latency_ms=0,
            cache_hit=False,
        )

        if cache is not None and image_record.image_hash:
            await self._cache_set(
                cache, image_record.image_hash, cache_key_task, analysis
            )

        return analysis

    # ---------------------------------
    # Cache helpers (best-effort — never block analysis on a
    # cache backend being unavailable)
    # ---------------------------------

    def _get_cache(self):

        try:
            from app.core.redis import redis_client
            from app.vision.vision_cache import VisionCache

            return VisionCache(redis_client)
        except Exception:
            return None

    async def _cache_get(self, cache, image_hash: str, task: str):

        try:
            import json

            raw = await cache.get(f"{image_hash}:{task}")
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _cache_set(self, cache, image_hash: str, task: str, analysis: dict):

        try:
            await cache.set(
                f"{image_hash}:{task}",
                analysis,
                ttl_seconds=settings.vision_cache_ttl_seconds,
            )
        except Exception:
            pass
