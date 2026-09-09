"""Sync result reporting."""

from __future__ import annotations

from dataclasses import dataclass, field


QUALITY_FIELDS = ("name", "price", "image_url", "product_url")


@dataclass
class SyncResult:
    store_id: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    stock_zeroed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    mapping_validation: dict | None = None
    data_quality: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.data_quality:
            self.data_quality = {
                "products": 0,
                "source_rows": 0,
                "skipped_rows": 0,
                "fields": {
                    field: {"present": 0, "missing": 0}
                    for field in QUALITY_FIELDS
                },
            }

    def record_quality(self, product: dict | None, *, source_row: bool = True):
        """Record field-level coverage for one normalized product row."""
        if source_row:
            self.data_quality["source_rows"] += 1
        if product is None:
            self.data_quality["skipped_rows"] += 1
            return

        self.data_quality["products"] += 1
        fields = self.data_quality["fields"]
        for field in QUALITY_FIELDS:
            value = product.get(field)
            present = value is not None and value != ""
            fields[field]["present" if present else "missing"] += 1

    def data_quality_report(self) -> dict:
        """Return a merchant-friendly quality report with stable field counts."""
        report = {
            "products": self.data_quality["products"],
            "source_rows": self.data_quality["source_rows"],
            "skipped_rows": self.data_quality["skipped_rows"],
            "fields": {},
        }
        for field, counts in self.data_quality["fields"].items():
            report["fields"][field] = {
                "present": counts["present"],
                "missing": counts["missing"],
            }
        return report

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
            "mapping_validation": self.mapping_validation,
            "data_quality": self.data_quality_report(),
            "success": self.success,
        }
