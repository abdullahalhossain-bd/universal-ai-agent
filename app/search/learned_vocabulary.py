"""Tenant-safe learned vocabulary boundary.

The old implementation stored LLM classifications in one global table keyed
only by ``term``. That allowed a classification learned from merchant A to
change search behavior for merchant B. A shared/global learning cache is not
acceptable in a multi-tenant commerce system.

The chat pipeline still calls these helpers for backward compatibility, but
persistent cross-store learning is intentionally disabled until a store-
scoped schema (``store_id + term``) is introduced. Returning ``None`` makes
unknown terms fall back to the normal store-local catalog logic and keeps
merchant behavior isolated across workers, restarts, and deployments.
"""

from sqlalchemy.orm import Session

from app.db.models import LearnedVocabulary


def normalize_term(term: str) -> str:
    """Lowercase + strip punctuation so callers retain the old normalization."""
    punctuation = ".,!?;:()[]{}\"'\u201c\u201d\u2018\u2019"
    return (term or "").strip(punctuation).strip().lower()


def lookup(db: Session, term: str) -> LearnedVocabulary | None:
    """Never return a cross-tenant learned entry.

    ``LearnedVocabulary`` is legacy/global schema without a store_id. Using it
    from a tenant request would violate isolation, so it is deliberately not
    consulted by the runtime search path.
    """
    normalize_term(term)
    return None


def remember_stopword(db: Session, term: str) -> None:
    """Compatibility no-op; global learned state must not be persisted."""
    normalize_term(term)
    return None


def remember_synonym(db: Session, term: str, resolved_value: str) -> None:
    """Compatibility no-op; global learned state must not be persisted."""
    normalize_term(term)
    normalize_term(resolved_value)
    return None
