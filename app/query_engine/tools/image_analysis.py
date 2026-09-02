"""
Image analysis tool for the query_engine plan executor.

Fully wired to the real `ChatImage` table (via
`app.images.repository.ImageRepository`) and the real vision
provider (via `app.vision.vision_service.VisionService`), mirroring
`ChatService.handle_image` in app/chat/service.py - same
store-scoped image lookup, same budget-aware vision call, same
`ProductMatcher` ranking. If the two ever need to diverge, extract a
shared helper instead of copy-drifting (same rule as
`product_search`/`knowledge_search` - see app/ARCHITECTURE_CLEANUP.md
item 3).

Requires a DB session bound via `bind_db()` before `execute()` is
called, same as `ProductSearchTool`/`StockTool`. Any failure
(missing db, missing image_id, unknown image, budget exceeded,
provider failure) is returned as `{"error": ...}` rather than
raised, so a bad image never blows up the whole plan - same contract
`PlanExecutor.run` already relies on for `ProductSearchTool`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.query_engine.tools.base import BaseTool
from app.db.models import Store
from app.images.repository import ImageRepository
from app.vision.vision_service import VisionService, VisionBudgetExceededError
from app.vision.vision_router import VisionAnalysisError
from app.vision.product_matcher import ProductMatcher


class ImageAnalysisTool(BaseTool):

    name = "image_analysis"
    description = "Analyze uploaded image to extract product attributes"

    def __init__(self, db: Session | None = None):
        self._db = db

    def bind_db(self, db: Session) -> "ImageAnalysisTool":
        self._db = db
        return self

    async def execute(
        self,
        tenant_id: str,
        filters: dict | None = None,
        query: str | None = None,
        **kwargs,
    ):

        if self._db is None:
            return {
                "error": (
                    "ImageAnalysisTool requires a database "
                    "session (bind_db)."
                )
            }

        filters = filters or {}

        image_id = filters.get("image_id")

        if not image_id:
            return {
                "error": "image_id is required in filters for image_analysis"
            }

        image_record = ImageRepository(self._db).get(
            store_id=tenant_id,
            image_id=image_id,
        )

        if image_record is None:
            return {"error": f"Image not found: {image_id}"}

        store = (
            self._db.query(Store)
            .filter(Store.id == tenant_id)
            .first()
        )

        if store is None:
            return {"error": f"Store not found: {tenant_id}"}

        question = filters.get("question") or query
        task = "image_question" if question else "product_match"

        try:
            analysis = await VisionService(db=self._db).analyze(
                store=store,
                image_record=image_record,
                task=task,
                question=question,
            )
        except VisionBudgetExceededError as exc:
            return {"error": str(exc)}
        except VisionAnalysisError as exc:
            return {"error": str(exc)}

        if task == "image_question":
            return {"analysis": analysis}

        matched_products = ProductMatcher(self._db).match(
            store_id=tenant_id,
            analysis=analysis,
            limit=filters.get("limit", 5),
        )

        return {
            "analysis": analysis,
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "price": (
                        float(product.price)
                        if product.price is not None
                        else None
                    ),
                    "image_url": product.image_url,
                    "product_url": product.product_url,
                }
                for product in matched_products
            ],
        }
