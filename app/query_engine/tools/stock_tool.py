"""
Real-time Stock Tool.

Product promise:
  "Customer can know right now whether a product is available."

Architecture:
  Customer query
    → Stock service
    → Freshness check
    → Cache (local products table)  OR  live merchant DB
    → Current stock

Rules:
  - Never blindly cache stock answers for long periods.
  - Prefer local catalog stock when fresh enough.
  - On stale / miss → mark as cache_stale; never invent numbers.
  - AI must never hallucinate stock.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.query_engine.tools.base import BaseTool
from app.db.models import Product, DataSource

logger = logging.getLogger("app.stock")

# How long local stock is considered "fresh enough" without a live hit.
DEFAULT_FRESHNESS_SECONDS = 300


@dataclass
class StockResult:
    product_id: str
    store_id: str
    stock: float | None
    in_stock: bool
    source: str  # "cache" | "cache_stale" | "unavailable"
    freshness_seconds: float | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "store_id": self.store_id,
            "stock": self.stock,
            "in_stock": self.in_stock,
            "source": self.source,
            "freshness_seconds": self.freshness_seconds,
            "message": self.message,
        }


class StockService:
    """Store-scoped stock lookup with freshness policy."""

    def __init__(
        self,
        db: Session,
        *,
        freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
    ):
        self.db = db
        self.freshness_seconds = freshness_seconds

    def get_local_stock(
        self,
        store_id: str,
        product_id: str,
    ) -> Product | None:
        return (
            self.db.query(Product)
            .filter(
                Product.store_id == store_id,
                Product.id == product_id,
            )
            .first()
        )

    def _datasource_last_sync_age(
        self,
        store_id: str,
    ) -> float | None:
        """
        Age in seconds of the most recent datasource activity for this store.
        Returns None if unknown.
        """
        ds = (
            self.db.query(DataSource)
            .filter(
                DataSource.store_id == store_id,
                DataSource.active.is_(True),
            )
            .order_by(DataSource.updated_at.desc())
            .first()
        )
        if ds is None:
            return None

        last = getattr(ds, "last_sync_at", None) or getattr(
            ds, "updated_at", None
        )
        if last is None:
            return None

        if getattr(last, "tzinfo", None) is None:
            last = last.replace(tzinfo=timezone.utc)

        age = (datetime.now(timezone.utc) - last).total_seconds()
        return max(age, 0.0)

    def check(
        self,
        store_id: str,
        product_id: str,
        *,
        force_live: bool = False,
    ) -> StockResult:
        product = self.get_local_stock(store_id, product_id)

        if product is None:
            return StockResult(
                product_id=product_id,
                store_id=store_id,
                stock=None,
                in_stock=False,
                source="unavailable",
                message="Product not found in catalog.",
            )

        age = self._datasource_last_sync_age(store_id)
        stock_val = (
            float(product.stock)
            if product.stock is not None
            else None
        )
        in_stock = bool(stock_val is not None and stock_val > 0)
        msg = (
            f"In stock ({stock_val:g})"
            if in_stock
            else "Out of stock"
        )

        if (
            not force_live
            and age is not None
            and age <= self.freshness_seconds
        ):
            return StockResult(
                product_id=product_id,
                store_id=store_id,
                stock=stock_val,
                in_stock=in_stock,
                source="cache",
                freshness_seconds=age,
                message=msg,
            )

        logger.info(
            "stock from local catalog (age=%s force=%s) store=%s product=%s",
            age,
            force_live,
            store_id,
            product_id,
        )

        return StockResult(
            product_id=product_id,
            store_id=store_id,
            stock=stock_val,
            in_stock=in_stock,
            source="cache_stale",
            freshness_seconds=age,
            message=msg,
        )

    def check_many(
        self,
        store_id: str,
        product_ids: list[str],
    ) -> list[StockResult]:
        return [self.check(store_id, pid) for pid in product_ids]


class StockTool(BaseTool):
    """
    Query-engine tool interface.
    Always returns structured stock — never free-form LLM guesses.
    """

    name = "stock"
    description = (
        "Check live stock for a product "
        "(always fresh policy, never hallucinated)"
    )

    def __init__(self, db: Session | None = None):
        self._db = db

    def bind_db(self, db: Session) -> "StockTool":
        self._db = db
        return self

    async def execute(
        self,
        tenant_id: str,
        product_id: str | None = None,
        product_ids: list[str] | None = None,
        force_live: bool = False,
        **kwargs,
    ):
        if self._db is None:
            return {
                "error": "StockTool requires a database session (bind_db)."
            }

        service = StockService(self._db)

        if product_ids:
            results = service.check_many(tenant_id, product_ids)
            return {"items": [r.to_dict() for r in results]}

        if not product_id:
            return {"error": "product_id or product_ids required"}

        result = service.check(
            tenant_id,
            product_id,
            force_live=force_live,
        )
        return result.to_dict()
