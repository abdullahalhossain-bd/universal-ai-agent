from app.connectors.field_hints import FIELD_HINTS
from app.connectors.field_scoring import normalize


def classify_field(column_name: str):
    """Return the canonical product field for an obvious source-column alias."""
    normalized = normalize(column_name)

    matches = [
        field
        for field, aliases in FIELD_HINTS.items()
        if normalized in {normalize(alias) for alias in aliases}
    ]

    # A source column should have one canonical meaning. Ambiguous aliases
    # (for example a generic 'type') are intentionally not auto-classified.
    return matches[0] if len(matches) == 1 else None
