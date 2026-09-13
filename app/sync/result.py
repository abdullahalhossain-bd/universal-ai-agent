"""Sync result reporting and deterministic data-quality summaries."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable
from app.sync.quality import VALID_CURRENCIES, valid_http_url, valid_source_http_url, normalize_name

QUALITY_FIELDS = ("name", "price", "image_url", "product_url")


def _number(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


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
    duplicate_candidates: list[dict] = field(default_factory=list)
    invalid_data: dict = field(default_factory=dict)
    invalid_counts: dict = field(default_factory=dict)
    reconciliation: dict = field(default_factory=dict)
    stale: dict = field(default_factory=dict)
    schema_drift: dict = field(default_factory=dict)
    repair_suggestions: list[dict] = field(default_factory=list)
    price_changes: list[dict] = field(default_factory=list)
    stock_changes: list[dict] = field(default_factory=list)
    issue_sink: Callable[[str, dict], None] | None = field(default=None, repr=False, compare=False)
    _seen_names: dict = field(default_factory=dict, repr=False)
    _seen_skus: set = field(default_factory=set, repr=False)
    _seen_ids: set = field(default_factory=set, repr=False)
    _duplicate_id_count: int = 0
    _duplicate_sku_count: int = 0
    _duplicate_name_count: int = 0
    _price_increased: int = 0
    _price_decreased: int = 0
    _stock_out: int = 0
    _stock_back: int = 0
    _stock_other: int = 0

    def __post_init__(self):
        if not self.data_quality:
            self.data_quality = {
                "products": 0, "source_rows": 0, "skipped_rows": 0,
                "fields": {f: {"present": 0, "missing": 0} for f in QUALITY_FIELDS},
                "issue_samples": {},
            }

    def _issue(self, field: str, item: dict, *, issue_type: str | None = None):
        if self.issue_sink is not None:
            try:
                self.issue_sink(field, {"issue_type": issue_type or field, **item})
            except Exception:
                pass
        bucket = self.data_quality.setdefault("issue_samples", {}).setdefault(field, [])
        if len(bucket) < 1000:
            bucket.append(item)

    def _invalid(self, key, product):
        self.invalid_counts[key] = self.invalid_counts.get(key, 0) + 1
        bucket = self.invalid_data.setdefault(key, [])
        item = {"id": str(product.get("id")), "name": product.get("name")}
        if len(bucket) < 100:
            bucket.append(item)
        self._issue(key, item, issue_type="invalid_data")

    def record_quality(self, p, *, source_row=True):
        if source_row:
            self.data_quality["source_rows"] += 1
        if p is None:
            self.data_quality["skipped_rows"] += 1
            return
        self.data_quality["products"] += 1
        pid = str(p.get("id") or "").strip()
        for f in QUALITY_FIELDS:
            v = p.get(f)
            state = "present" if v is not None and v != "" else "missing"
            self.data_quality["fields"][f][state] += 1
            if state == "missing":
                self._issue(f, {"id": pid, "name": p.get("name"), "reason": "missing"}, issue_type="missing_field")
        if pid and pid in self._seen_ids:
            self._duplicate_id_count += 1
            self._issue("duplicate_id", {"id": pid, "name": p.get("name"), "reason": "same source ID appeared more than once"}, issue_type="duplicate")
        if pid:
            self._seen_ids.add(pid)
        name = normalize_name(p.get("name"))
        attrs = p.get("attributes") if isinstance(p.get("attributes"), dict) else {}
        sku = p.get("sku") or attrs.get("sku") or attrs.get("product_code") or attrs.get("item_code")
        if sku:
            k = str(sku).strip().casefold()
            if k in self._seen_skus:
                self._duplicate_sku_count += 1
                if k not in self.duplicate_skus and len(self.duplicate_skus) < 1000:
                    self.duplicate_skus.append(k)
                self._issue("duplicate_sku", {"sku": k, "id": pid, "name": p.get("name")}, issue_type="duplicate")
            elif len(self._seen_skus) < 200000:
                self._seen_skus.add(k)
        if name:
            prior = self._seen_names.get(name)
            if prior is not None:
                self._duplicate_name_count += 1
                if name not in self.duplicate_names and len(self.duplicate_names) < 1000:
                    self.duplicate_names.append(name)
                old_price = _number(prior.get("price")); new_price = _number(p.get("price"))
                same_price = old_price is not None and new_price is not None and old_price == new_price
                same_cat = bool(p.get("category")) and normalize_name(p.get("category")) == normalize_name(prior.get("category"))
                confidence = 95 if same_price and same_cat else (80 if same_price or same_cat else 60)
                candidate = {
                    "id_a": prior.get("id"), "id_b": pid, "name": p.get("name"),
                    "confidence_pct": confidence,
                    "classification": "strong_candidate" if confidence >= 90 else ("candidate" if confidence >= 70 else "possible"),
                    "signals": ["same_name"] + (["same_price"] if same_price else []) + (["same_category"] if same_cat else []),
                }
                if len(self.duplicate_candidates) < 1000:
                    self.duplicate_candidates.append(candidate)
                self._issue("duplicate_name", candidate, issue_type="duplicate")
            self._seen_names[name] = {"id": pid, "price": p.get("price"), "category": p.get("category")}
        if not str(p.get("name") or "").strip():
            self._invalid("empty_name", p)
        price = _number(p.get("price"))
        if p.get("price") is not None and price is None:
            self._invalid("invalid_price", p)
        elif price is not None and price < 0:
            self._invalid("negative_price", p)
        stock = _number(p.get("stock"))
        if p.get("stock") is not None and stock is None:
            self._invalid("invalid_stock", p)
        elif stock is not None and stock < 0:
            self._invalid("invalid_stock", p)
        if p.get("currency") and str(p["currency"]).upper() not in VALID_CURRENCIES:
            self._invalid("invalid_currency", p)
        if p.get("product_url") and not valid_source_http_url(p["product_url"]):
            self._invalid("malformed_url", p)
        if p.get("image_url") and not valid_source_http_url(p["image_url"]):
            self._invalid("invalid_image_url", p)

    def record_duplicate(self, pid):
        value = str(pid)
        self._duplicate_id_count += 1
        if value not in self.duplicate_ids and len(self.duplicate_ids) < 1000:
            self.duplicate_ids.append(value)
        self._issue("duplicate_id", {"id": value, "reason": "same source ID appeared more than once"}, issue_type="duplicate")

    def record_price_change(self, pid, name, old, new):
        old_n = _number(old); new_n = _number(new)
        if old_n is None or new_n is None or old_n == new_n:
            return
        if new_n > old_n: self._price_increased += 1
        else: self._price_decreased += 1
        item = {"id": str(pid), "name": name, "old": old, "new": new, "direction": "increased" if new_n > old_n else "decreased"}
        self._issue("price_changes", item, issue_type="price_change")
        if len(self.price_changes) < 1000:
            self.price_changes.append(item)

    def record_stock_change(self, pid, name, old, new):
        old_n = _number(old); new_n = _number(new)
        if old_n is None or new_n is None or old_n == new_n:
            return
        state = "became_out_of_stock" if old_n > 0 and new_n <= 0 else ("came_back_in_stock" if old_n <= 0 and new_n > 0 else "changed")
        if state == "became_out_of_stock": self._stock_out += 1
        elif state == "came_back_in_stock": self._stock_back += 1
        else: self._stock_other += 1
        item = {"id": str(pid), "name": name, "old": old, "new": new, "state": state}
        self._issue("stock_changes", item, issue_type="stock_change")
        if len(self.stock_changes) < 1000:
            self.stock_changes.append(item)

    def data_quality_report(self):
        fields = {}
        for f, c in self.data_quality["fields"].items():
            total = c["present"] + c["missing"]
            fields[f] = {"present": c["present"], "missing": c["missing"], "coverage_pct": round(c["present"] / total * 100, 2) if total else 100.0}
        d = {
            "duplicate_id_count": self._duplicate_id_count,
            "duplicate_sku_count": self._duplicate_sku_count,
            "possible_duplicate_name_count": self._duplicate_name_count,
            "possible_duplicate_count": self._duplicate_name_count,
            "sample_ids": self.duplicate_ids[:20], "sample_skus": self.duplicate_skus[:20],
            "sample_names": self.duplicate_names[:20], "candidates": self.duplicate_candidates[:20],
        }
        return {"products": self.data_quality["products"], "source_rows": self.data_quality["source_rows"], "skipped_rows": self.data_quality["skipped_rows"], "fields": fields, "duplicates": d, "invalid_data": self.invalid_data, "invalid_counts": self.invalid_counts, "broken_media": self.data_quality.get("broken_media", 0), "issue_samples": self.data_quality.get("issue_samples", {})}

    def calculate_health_score(self):
        r = self.data_quality_report(); f = r["fields"]; total = max(1, int(r["products"]))
        base = f["name"]["coverage_pct"] * .30 + f["price"]["coverage_pct"] * .25 + f["image_url"]["coverage_pct"] * .20 + f["product_url"]["coverage_pct"] * .25
        invalid_products = set()
        for items in self.invalid_data.values():
            for item in items:
                if item.get("id"): invalid_products.add(str(item["id"]))
        invalid_rate = len(invalid_products) / total
        dup_rate = len(set(self.duplicate_ids)) / total + len(set(self.duplicate_skus)) / total
        broken_rate = float(r.get("broken_media", 0)) / total
        skipped_rate = self.skipped / max(1, int(r["source_rows"]))
        penalty = min(12, invalid_rate * 100 * .20) + min(10, dup_rate * 100 * .10) + min(5, skipped_rate * 5) + min(10, broken_rate * 100 * .10)
        rec = self.reconciliation or {}
        if rec and not rec.get("reconciled", False):
            penalty += min(10, float(rec.get("unexplained", 0) or 0) / total * 10)
        return max(0, min(100, round(base - penalty)))

    def set_reconciliation(self, *, source_rows, accepted_products, db_count, rejected=0, duplicates=0, known_stale=0):
        expected = max(0, int(accepted_products)); delta = db_count - expected; unexplained = max(0, abs(delta) - known_stale)
        self.reconciliation = {"source_rows": int(source_rows), "unique_source_ids": max(0, expected + int(duplicates)), "accepted_products": expected, "db_count": int(db_count), "expected_db_count": expected, "difference": int(delta), "missing_in_db": max(0, -delta), "stale_in_db": max(0, delta), "known_stale": int(known_stale), "rejected": int(rejected), "duplicates": int(duplicates), "unexplained": int(unexplained), "reconciled": unexplained == 0}

    @property
    def seen_ids(self): return set(self._seen_ids)
    @property
    def success(self): return not self.errors or (self.created + self.updated + self.unchanged > 0)

    def to_dict(self):
        return {"store_id": self.store_id, "created": self.created, "updated": self.updated, "unchanged": self.unchanged, "stock_zeroed": self.stock_zeroed, "skipped": self.skipped, "errors": list(self.errors), "mapping_validation": self.mapping_validation, "data_quality": self.data_quality_report(), "health_score": self.calculate_health_score(), "reconciliation": self.reconciliation, "stale": self.stale, "schema_drift": self.schema_drift, "repair_suggestions": self.repair_suggestions, "price_changes": {"total": self._price_increased + self._price_decreased, "increased": self._price_increased, "decreased": self._price_decreased, "items": self.price_changes[:100]}, "stock_changes": {"total": self._stock_out + self._stock_back + self._stock_other, "became_out_of_stock": self._stock_out, "came_back_in_stock": self._stock_back, "other": self._stock_other, "items": self.stock_changes[:100]}, "success": self.success}
