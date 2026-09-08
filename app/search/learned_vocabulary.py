"""
Global, cross-store cache of words the rule-based search planner/matcher
couldn't classify and had to ask the LLM about.

Two kinds of learned entries:
  - "stopword": the word carries no product meaning (a question word,
    quantity word, grammar particle, etc. — e.g. "কয়ডা") and should be
    dropped from future search terms without asking the LLM again.
  - "synonym":  the word IS product-related but misspelled/dialectal;
    `resolved_value` holds the corrected keyword to search with instead.

Deliberately NOT scoped by store_id — see LearnedVocabulary model
docstring in app/db/models.py for why that's safe and desirable here.
"""

from sqlalchemy.orm import Session

from app.db.models import LearnedVocabulary

_PUNCTUATION = ".,!?;:()[]{}\"'\u201c\u201d\u2018\u2019"


def normalize_term(term: str) -> str:
    """Lowercase + strip punctuation so lookups are case/format-insensitive."""
    return (term or "").strip(_PUNCTUATION).strip().lower()


def lookup(db: Session, term: str) -> LearnedVocabulary | None:
    """Return the cached classification for `term`, or None if unseen."""
    normalized = normalize_term(term)
    if not normalized:
        return None
    return db.get(LearnedVocabulary, normalized)


def remember_stopword(db: Session, term: str) -> None:
    """Cache `term` as a filler/non-product word, globally, for next time."""
    _save(db, term, kind="stopword", resolved_value=None)


def remember_synonym(db: Session, term: str, resolved_value: str) -> None:
    """Cache `term` as a misspelling/dialect form of `resolved_value`."""
    _save(db, term, kind="synonym", resolved_value=resolved_value)


def _save(db: Session, term: str, kind: str, resolved_value: str | None) -> None:
    normalized = normalize_term(term)
    if not normalized:
        return

    existing = db.get(LearnedVocabulary, normalized)

    if existing is not None:
        existing.kind = kind
        existing.resolved_value = resolved_value
    else:
        db.add(
            LearnedVocabulary(
                term=normalized,
                kind=kind,
                resolved_value=resolved_value,
            )
        )

    db.commit()