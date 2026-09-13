from app.connectors.field_mapper import (
    build_candidate_mapping,
    resolve_mapping,
)
from app.connectors.mapping_candidates import MappingCandidate


class MappingEngine:
    """Backward-compatible facade over the unified mapping pipeline."""

    def suggest(self, columns: list[str]):
        # Legacy callers only provide names, so build the same candidate model
        # used by the datasource mapper and then apply one-to-one resolution.
        column_models = [
            {"name": column}
            for column in columns
        ]
        candidates = build_candidate_mapping(column_models)
        resolved = resolve_mapping(candidates)

        return [
            MappingCandidate(
                field=field,
                column=data["column"],
                confidence=data["confidence"],
                reason="Unified canonical alias matched with automatic confidence scoring",
            )
            for field, data in resolved["resolved"].items()
        ]
