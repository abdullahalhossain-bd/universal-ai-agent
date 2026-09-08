"""Sync result reporting."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyncResult:
    store_id: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    stock_zeroed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors or (
            self.created + self.updated + self.unchanged > 0
        )

    def to_dict(self) -> dict:
        return {
            "store_id": self.store_id,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "stock_zeroed": self.stock_zeroed,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "success": self.success,
        }
