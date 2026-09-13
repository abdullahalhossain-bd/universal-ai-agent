"""Production mapping confirmation with incremental-sync metadata detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from rapidfuzz.fuzz import ratio

from app.connectors.mapping_decision import CRITICAL_FIELDS, should_auto_accept
from app.connectors.mapping_engine import MappingEngine
from app.connectors.mapping_candidates import MappingCandidate
from app.discovery.engine import discover_field_mapping
from app.discovery.vocabulary import FIELD_SYNONYMS

AUTO_ACCEPT_THRESHOLD = 0.90
ASK_MERCHANT_THRESHOLD = 0.70
SYNC_TIMESTAMP_HINTS = {
    "updated_at": ("updated_at", "updatedat", "updated_on", "modified_at", "modified_on", "last_updated", "last_modified"),
    "created_at": ("created_at", "createdat", "created_on", "date_created", "inserted_at", "added_at"),
}


@dataclass
class FieldMappingDecision:
    semantic_field: str
    column: str | None
    confidence: float
    status: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass
class MappingConfirmationResult:
    table: str
    decisions: list[FieldMappingDecision]
    auto_accepted: dict[str, str]
    needs_confirmation: list[FieldMappingDecision]
    manual_required: list[FieldMappingDecision]
    ready_for_sync: bool

    def to_dict(self) -> dict[str, Any]:
        ask = {d.semantic_field: {"suggested_column": d.column, "confidence": round(d.confidence, 3), "status": d.status, "candidates": d.candidates, "reason": d.reason} for d in self.needs_confirmation}
        manual = {d.semantic_field: {"suggested_column": d.column, "confidence": round(d.confidence, 3), "status": d.status, "candidates": d.candidates, "reason": d.reason} for d in self.manual_required}
        return {
            "table": self.table,
            "auto_accepted": self.auto_accepted,
            "needs_confirmation": [{"field": d.semantic_field, "suggested_column": d.column, "confidence": round(d.confidence, 3), "status": d.status, "candidates": d.candidates, "reason": d.reason} for d in self.needs_confirmation],
            "manual_required": [{"field": d.semantic_field, "suggested_column": d.column, "confidence": round(d.confidence, 3), "candidates": d.candidates, "reason": d.reason} for d in self.manual_required],
            "ask": ask,
            "manual": manual,
            "ready_for_sync": self.ready_for_sync,
            "decisions": [{"field": d.semantic_field, "column": d.column, "confidence": round(d.confidence, 3), "status": d.status} for d in self.decisions],
        }


class MappingConfirmationService:
    """Discover → score → de-conflict → confirm merchant product fields."""
    def __init__(self):
        self._name_engine = MappingEngine()

    @staticmethod
    def _ranked_candidates(discovered, name_only, field):
        raw = []
        disc = discovered.get(field)
        if disc: raw.extend(disc.get("candidates") or [])
        name_cand = name_only.get(field)
        if name_cand: raw.append({"column": name_cand.column, "confidence": name_cand.confidence, "reason": name_cand.reason})
        best_by_column = {}
        for candidate in raw:
            column = candidate.get("column")
            if not column: continue
            confidence = float(candidate.get("confidence", candidate.get("score", 0)))
            if column not in best_by_column or confidence > float(best_by_column[column].get("confidence", 0)):
                item = dict(candidate); item["confidence"] = confidence; best_by_column[column] = item
        return sorted(best_by_column.values(), key=lambda x: float(x.get("confidence", 0)), reverse=True)

    @staticmethod
    def _sync_metadata_candidates(col_names):
        result = {}
        normalized = {name: name.lower().strip().replace("-", "_").replace(" ", "_") for name in col_names}
        for field, hints in SYNC_TIMESTAMP_HINTS.items():
            matches = []
            for original, name in normalized.items():
                best = max((ratio(name, hint) / 100 for hint in hints), default=0)
                if name in hints: best = 1.0
                if best >= 0.85:
                    matches.append({"column": original, "confidence": best, "reason": "timestamp column detected for incremental sync"})
            if matches:
                result[field] = {"candidates": sorted(matches, key=lambda x: x["confidence"], reverse=True)}
        return result

    def confirm(self, table, columns, sample_data=None, *, merchant_overrides=None):
        sample_data = sample_data or {}; merchant_overrides = merchant_overrides or {}
        col_dicts = []; col_names = []
        for c in columns:
            if isinstance(c, str): col_dicts.append({"name": c, "type": None}); col_names.append(c)
            else: col_dicts.append(c); col_names.append(c["name"])
        discovered = discover_field_mapping(col_dicts, sample_data)
        discovered.update(self._sync_metadata_candidates(col_names))
        name_only = {c.field: c for c in self._name_engine.suggest(col_names)}
        decisions = []; auto_accepted = {}; needs_confirmation = []; manual_required = []; used_columns = set()
        field_order = [f for f in ("id", "name", "price", "stock", "image_url", "category", "description", "brand", "sku", "updated_at", "created_at") if f in discovered or f in FIELD_SYNONYMS]
        for semantic_field in field_order:
            if semantic_field in merchant_overrides:
                col = merchant_overrides[semantic_field]
                if col not in col_names:
                    d = FieldMappingDecision(semantic_field, None, 0, "manual", [], "merchant-selected column does not exist"); decisions.append(d); manual_required.append(d); continue
                if col in used_columns:
                    d = FieldMappingDecision(semantic_field, col, 1, "needs_confirmation", [], "merchant selection conflicts with another mapped field"); decisions.append(d); needs_confirmation.append(d); continue
                d = FieldMappingDecision(semantic_field, col, 1, "auto_accepted", [], "merchant confirmed"); decisions.append(d); auto_accepted[semantic_field] = col; used_columns.add(col); continue
            candidates = self._ranked_candidates(discovered, name_only, semantic_field)
            available = [c for c in candidates if c["column"] not in used_columns]
            best = available[0] if available else None
            if not best:
                d = FieldMappingDecision(semantic_field, None, 0, "unmapped", candidates[:3], "no candidate found"); decisions.append(d)
                if semantic_field in CRITICAL_FIELDS: manual_required.append(d)
                continue
            best_col = best["column"]; best_conf = float(best["confidence"]); top = available[:3]
            cand_objs = [MappingCandidate(field=semantic_field, column=c["column"], confidence=float(c.get("confidence", 0)), reason=c.get("reason", "")) for c in top]
            is_timestamp = semantic_field in SYNC_TIMESTAMP_HINTS
            if should_auto_accept(cand_objs, semantic_field) or (semantic_field not in CRITICAL_FIELDS and best_conf >= AUTO_ACCEPT_THRESHOLD):
                d = FieldMappingDecision(semantic_field, best_col, best_conf, "auto_accepted", top, "best candidate above threshold"); decisions.append(d); auto_accepted[semantic_field] = best_col; used_columns.add(best_col)
            elif best_conf >= ASK_MERCHANT_THRESHOLD:
                d = FieldMappingDecision(semantic_field, best_col, best_conf, "needs_confirmation", top, "confidence in merchant-review range"); decisions.append(d); needs_confirmation.append(d)
            else:
                d = FieldMappingDecision(semantic_field, best_col, best_conf, "manual", top, "confidence below threshold"); decisions.append(d); manual_required.append(d)
        return MappingConfirmationResult(table, decisions, auto_accepted, needs_confirmation, manual_required, "id" in auto_accepted and "name" in auto_accepted)

    def apply_merchant_choices(self, previous, choices):
        valid_columns = {d.column for d in previous.decisions if d.column}; used = set(); decisions = []; needs = []; manual = []
        for d in previous.decisions:
            if d.semantic_field in choices:
                col = choices[d.semantic_field]
                if col not in valid_columns:
                    nd = FieldMappingDecision(d.semantic_field, None, 0, "manual", d.candidates, "selected column is not in discovered schema"); decisions.append(nd); manual.append(nd)
                elif col in used:
                    nd = FieldMappingDecision(d.semantic_field, col, 1, "needs_confirmation", d.candidates, "selected column is already mapped"); decisions.append(nd); needs.append(nd)
                else:
                    nd = FieldMappingDecision(d.semantic_field, col, 1, "auto_accepted", d.candidates, "merchant confirmed"); decisions.append(nd); used.add(col)
            else:
                decisions.append(d)
                if d.status == "needs_confirmation": needs.append(d)
                elif d.status in ("manual", "unmapped"): manual.append(d)
                elif d.column: used.add(d.column)
        auto = {d.semantic_field: d.column for d in decisions if d.status == "auto_accepted" and d.column}
        return MappingConfirmationResult(previous.table, decisions, auto, needs, manual, "id" in auto and "name" in auto)

    def to_sync_mapping(self, result):
        return dict(result.auto_accepted)
