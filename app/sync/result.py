"""Sync result reporting and deterministic data-quality summaries."""
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
    duplicate_ids: list[str] = field(default_factory=list)
    duplicate_skus: list[str] = field(default_factory=list)
    duplicate_names: list[str] = field(default_factory=list)
    invalid_data: dict = field(default_factory=dict)
    reconciliation: dict = field(default_factory=dict)
    stale: dict = field(default_factory=dict)
    schema_drift: dict = field(default_factory=dict)
    repair_suggestions: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.data_quality:
            self.data_quality = {"products": 0, "source_rows": 0, "skipped_rows": 0, "fields": {field: {"present": 0, "missing": 0} for field in QUALITY_FIELDS}}

    def record_quality(self, product: dict | None, *, source_row: bool = True):
        if source_row: self.data_quality["source_rows"] += 1
        if product is None:
            self.data_quality["skipped_rows"] += 1
            return
        self.data_quality["products"] += 1
        for field in QUALITY_FIELDS:
            value = product.get(field)
            self.data_quality["fields"][field]["present" if value is not None and value != "" else "missing"] += 1

    def record_duplicate(self, product_id) -> None:
        value = str(product_id)
        if value not in self.duplicate_ids and len(self.duplicate_ids) < 1000:
            self.duplicate_ids.append(value)

    def data_quality_report(self) -> dict:
        report = {
            "products": self.data_quality["products"],
            "source_rows": self.data_quality["source_rows"],
            "skipped_rows": self.data_quality["skipped_rows"],
            "fields": {},
            "duplicates": {
                "duplicate_id_count": len(self.duplicate_ids),
                "duplicate_sku_count": len(self.duplicate_skus),
                "possible_duplicate_name_count": len(self.duplicate_names),
                "sample_ids": self.duplicate_ids[:20],
                "sample_skus": self.duplicate_skus[:20],
                "sample_names": self.duplicate_names[:20],
            },
            "invalid_data": self.invalid_data,
        }
        for field, counts in self.data_quality["fields"].items():
            total = counts["present"] + counts["missing"]
            report["fields"][field] = {"present": counts["present"], "missing": counts["missing"], "coverage_pct": round((counts["present"] / total) * 100, 2) if total else 100.0}
        return report

    def calculate_health_score(self) -> int:
        fields = self.data_quality_report()["fields"]
        score = fields["name"]["coverage_pct"] * .30 + fields["price"]["coverage_pct"] * .25 + fields["image_url"]["coverage_pct"] * .20 + fields["product_url"]["coverage_pct"] * .25
        duplicate_penalty = min(len(self.duplicate_ids) + len(self.duplicate_skus), 20) * .5
        invalid_penalty = min(sum(len(v) for v in self.invalid_data.values() if isinstance(v, list)), 40) * .25
        skipped_penalty = min(self.data_quality["skipped_rows"], 20) * .25
        return max(0, min(100, round(score - duplicate_penalty - invalid_penalty - skipped_penalty)))

    def set_reconciliation(self, *, source_count: int, db_count: int, rejected: int = 0, duplicates: int = 0):
        difference = source_count - db_count
        unexplained = max(0, abs(difference) - rejected - duplicates)
        self.reconciliation = {"source_count": source_count, "db_count": db_count, "difference": difference, "reconciled": difference == 0, "reasons": {"rejected": rejected, "duplicates": duplicates, "unexplained": unexplained}}

    @property
    def success(self) -> bool:
        return not self.errors or (self.created + self.updated + self.unchanged > 0)

    def to_dict(self) -> dict:
        return {"store_id": self.store_id, "created": self.created, "updated": self.updated, "unchanged": self.unchanged, "stock_zeroed": self.stock_zeroed, "skipped": self.skipped, "errors": list(self.errors), "mapping_validation": self.mapping_validation, "data_quality": self.data_quality_report(), "health_score": self.calculate_health_score(), "reconciliation": self.reconciliation, "stale": self.stale, "schema_drift": self.schema_drift, "repair_suggestions": self.repair_suggestions, "success": self.success}
