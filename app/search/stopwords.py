"""Lightweight fallback stopwords for natural-language search.

IMPORTANT:
    Stopwords are an optimization/fallback only. They are NOT the source of
    truth for query semantics. Merchant catalog vocabulary and semantic
    understanding should decide which words represent products, categories,
    brands, attributes, or user intent.

    In particular, Bengali/Banglish existence, quantity, pronoun and other
    conversational variations must not require an ever-growing dictionary.
"""

# Keep this deliberately small. These are high-confidence language/function
# tokens that are very unlikely to be merchant entities. Domain-specific
# vocabulary must come from the merchant catalog, not from this set.
STOPWORDS: set[str] = {
    # English articles / conjunctions / basic prepositions
    "a", "an", "the", "and", "or", "but", "of", "for", "to", "with", "on",
    "at", "from", "by", "in", "as", "than", "between", "around",

    # English auxiliary / question words (fallback only)
    "do", "does", "did", "is", "are", "am", "was", "were", "be", "been",
    "being", "will", "would", "can", "could", "should", "shall", "may",
    "might", "must", "what", "which", "where", "when", "how", "who", "whom",
    "why", "this", "that", "these", "those", "there", "here",

    # Common English conversational fillers
    "please", "plz", "pls", "hello", "hi", "hey", "thanks", "thank",

    # Bengali function words / particles with high confidence
    "এর", "র", "টা", "টি", "ও", "আর", "মধ্যে", "জন্য", "এটা", "এইটা",
    "ওটা", "ওইটা", "কোন", "কোনটা", "কোনটি", "কোনো",

    # Very common Banglish function words
    "er", "r", "ta", "ti", "gula", "gulo", "gulor", "eta", "eita", "ota",
    "oita", "ei", "oi", "egula", "ogula", "tar",
}

_PUNCTUATION = ".,!?;:()[]{}\"'“”‘’—–…"


def _normalize_token(value: str) -> str:
    return value.strip(_PUNCTUATION).lower()


def strip_stopwords(
    terms: list[str],
    store_terms: set[str] | None = None,
) -> list[str]:
    """Remove only fallback filler while preserving merchant entities.

    `store_terms` is checked FIRST. This is important for arbitrary merchant
    catalogs where a token that looks like a conversational word may actually
    be a product/brand/category name.
    """
    normalized_store_terms = {
        _normalize_token(str(term))
        for term in (store_terms or set())
        if str(term).strip()
    }

    filtered: list[str] = []
    for term in terms:
        cleaned = term.strip(_PUNCTUATION)
        if not cleaned:
            continue

        normalized = _normalize_token(cleaned)
        if normalized in normalized_store_terms:
            filtered.append(cleaned)
            continue

        if normalized in STOPWORDS:
            continue

        filtered.append(cleaned)

    return filtered
