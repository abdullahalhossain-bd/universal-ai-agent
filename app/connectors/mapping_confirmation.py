"""
Production Mapping Confirmation System.

Confidence rules (from product architecture):

  Confidence >= 0.90  → auto accept
  Confidence 0.70–0.89 → ask merchant
  Confidence < 0.70   → manual mapping required

Critical fields (id, name) require higher bar (>= 0.95) and
a clear gap over the runner-up before auto-accept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.connectors.mapping_decision import (
    CRITICAL_FIELDS,
    should_auto_accept,
)
from app.connectors.mapping_engine import MappingEngine
from app.connectors.mapping_candidates import MappingCandidate
from app.discovery.engine import discover_field_mapping
from app.discovery.vocabulary import FIELD_SYNONYMS


# Thresholds aligned with product promise
AUTO_ACCEPT_THRESHOLD = 0.90
ASK_MERCHANT_THRESHOLD = 0.70
CRITICAL_AUTO_ACCEPT = 0.95


@dataclass
class FieldMappingDecision:
    semantic_field: str
    column: str | None
    confidence: float
    status: str  # auto_accepted | needs_confirmation | manual | unmapped
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
        return {
            "table": self.table,
            "auto_accepted": self.auto_accepted,
            "needs_confirmation": [
                {
                    "field": d.semantic_field,
                    "suggested_column": d.column,
                    "confidence": round(d.confidence, 3),
                    "status": d.status,
                    "candidates": d.candidates,
                    "reason": d.reason,
                }
                for d in self.needs_confirmation
            ],
            "manual_required": [
                {
                    "field": d.semantic_field,
                    "confidence": round(d.confidence, 3),
                    "candidates": d.candidates,
                    "reason": d.reason,
                }
                for d in self.manual_required
            ],
            "ready_for_sync": self.ready_for_sync,
            "decisions": [
                {
                    "field": d.semantic_field,
                    "column": d.column,
                    "confidence": round(d.confidence, 3),
                    "status": d.status,
                }
                for d in self.decisions
            ],
        }


class MappingConfirmationService:
    """
    Runs discovery → scoring → decision for a merchant table.

    Usage in onboarding:
      1. Schema scan
      2. Sample values
      3. this.confirm(table, columns, samples)
      4. If ready_for_sync → proceed
         Else → return needs_confirmation / manual to merchant UI
    """

    def __init__(self):
        self._name_engine = MappingEngine()

    def confirm(
        self,
        table: str,
        columns: list[dict[str, Any]] | list[str],
        sample_data: dict[str, list] | None = None,
        *,
        merchant_overrides: dict[str, str] | None = None,
    ) -> MappingConfirmationResult:
        """
        columns: either [{"name": "...", "type": "..."}, ...] or plain names
        sample_data: {column_name: [sample values]}
        merchant_overrides: {semantic_field: column} already confirmed by merchant
        """
        sample_data = sample_data or {}
        merchant_overrides = merchant_overrides or {}

        # Normalize column list
        col_dicts: list[dict[str, Any]] = []
        col_names: list[str] = []
        for c in columns:
            if isinstance(c, str):
                col_dicts.append({"name": c, "type": None})
                col_names.append(c)
            else:
                col_dicts.append(c)
                col_names.append(c["name"])

        # Prefer discovery engine (name + type + sample) when samples available
        discovered = discover_field_mapping(col_dicts, sample_data)

        # Fallback / supplement with name-only MappingEngine
        name_only = {
            c.field: c
            for c in self._name_engine.suggest(col_names)
        }

        decisions: list[FieldMappingDecision] = []
        auto_accepted: dict[str, str] = {}
        needs_confirmation: list[FieldMappingDecision] = []
        manual_required: list[FieldMappingDecision] = []

        for semantic_field in FIELD_SYNONYMS.keys():
            # Merchant already confirmed
            if semantic_field in merchant_overrides:
                col = merchant_overrides[semantic_field]
                d = FieldMappingDecision(
                    semantic_field=semantic_field,
                    column=col,
                    confidence=1.0,
                    status="auto_accepted",
                    reason="merchant confirmed",
                )
                decisions.append(d)
                auto_accepted[semantic_field] = col
                continue

            disc = discovered.get(semantic_field)
            name_cand = name_only.get(semantic_field)

            best_col: str | None = None
            best_conf = 0.0
            candidates: list[dict[str, Any]] = []

            if disc:
                best_col = disc["column"]
                best_conf = float(disc["confidence"])
                candidates = disc.get("candidates") or [
                    {
                        "column": disc["column"],
                        "confidence": disc["confidence"],
                    }
                ]
            elif name_cand:
                best_col = name_cand.column
                best_conf = float(name_cand.confidence)
                candidates = [
                    {
                        "column": name_cand.column,
                        "confidence": name_cand.confidence,
                        "reason": name_cand.reason,
                    }
                ]

            # Apply decision rules
            if best_col is None or best_conf < ASK_MERCHANT_THRESHOLD:
                status = "manual" if best_col else "unmapped"
                d = FieldMappingDecision(
                    semantic_field=semantic_field,
                    column=best_col,
                    confidence=best_conf,
                    status=status,
                    candidates=candidates,
                    reason=(
                        "confidence below ask-merchant threshold"
                        if best_col
                        else "no candidate found"
                    ),
                )
                decisions.append(d)
                if semantic_field in ("id", "name"):
                    manual_required.append(d)
                elif best_col:
                    manual_required.append(d)
                continue

            # Build candidate objects for should_auto_accept
            cand_objs = [
                MappingCandidate(
                    field=semantic_field,
                    column=c.get("column", best_col),
                    confidence=float(c.get("confidence", 0)),
                    reason=c.get("reason", ""),
                )
                for c in candidates
            ]
            if not cand_objs and best_col:
                cand_objs = [
                    MappingCandidate(
                        field=semantic_field,
                        column=best_col,
                        confidence=best_conf,
                        reason="",
                    )
                ]

            if should_auto_accept(cand_objs, semantic_field) or (
                semantic_field not in CRITICAL_FIELDS
                and best_conf >= AUTO_ACCEPT_THRESHOLD
            ):
                status = "auto_accepted"
                d = FieldMappingDecision(
                    semantic_field=semantic_field,
                    column=best_col,
                    confidence=best_conf,
                    status=status,
                    candidates=candidates,
                    reason="confidence above auto-accept threshold",
                )
                decisions.append(d)
                auto_accepted[semantic_field] = best_col
            else:
                status = "needs_confirmation"
                d = FieldMappingDecision(
                    semantic_field=semantic_field,
                    column=best_col,
                    confidence=best_conf,
                    status=status,
                    candidates=candidates,
                    reason="confidence in ask-merchant range",
                )
                decisions.append(d)
                needs_confirmation.append(d)

        # Ready when required fields (id + name) are accepted
        ready = (
            "id" in auto_accepted
            and "name" in auto_accepted
            and not any(
                d.semantic_field in ("id", "name")
                for d in needs_confirmation + manual_required
            )
        )

        return MappingConfirmationResult(
            table=table,
            decisions=decisions,
            auto_accepted=auto_accepted,
            needs_confirmation=needs_confirmation,
            manual_required=manual_required,
            ready_for_sync=ready,
        )

    def apply_merchant_choices(
        self,
        previous: MappingConfirmationResult,
        choices: dict[str, str],
    ) -> MappingConfirmationResult:
        """
        Merchant confirms or overrides suggested columns.
        choices: {semantic_field: column}
        """
        merged = dict(previous.auto_accepted)
        merged.update(choices)

        # Rebuild decisions with overrides treated as accepted
        decisions: list[FieldMappingDecision] = []
        needs: list[FieldMappingDecision] = []
        manual: list[FieldMappingDecision] = []

        for d in previous.decisions:
            if d.semantic_field in choices:
                decisions.append(
                    FieldMappingDecision(
                        semantic_field=d.semantic_field,
                        column=choices[d.semantic_field],
                        confidence=1.0,
                        status="auto_accepted",
                        candidates=d.candidates,
                        reason="merchant confirmed",
                    )
                )
            else:
                decisions.append(d)
                if d.status == "needs_confirmation":
                    needs.append(d)
                elif d.status in ("manual", "unmapped"):
                    manual.append(d)

        auto = {
            d.semantic_field: d.column
            for d in decisions
            if d.status == "auto_accepted" and d.column
        }

        ready = "id" in auto and "name" in auto

        return MappingConfirmationResult(
            table=previous.table,
            decisions=decisions,
            auto_accepted=auto,
            needs_confirmation=needs,
            manual_required=manual,
            ready_for_sync=ready,
        )

    def to_sync_mapping(
        self,
        result: MappingConfirmationResult,
    ) -> dict[str, str]:
        """
        Produce the flat {semantic_field: column} mapping used by
        ProductSyncService / normalize_row.
        """
        return dict(result.auto_accepted)
