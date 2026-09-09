import difflib
import re

from app.planner.models import Intent, PlannedAction, ProductFilters
from app.search.stopwords import STOPWORDS as SHARED_STOPWORDS

# Product/entity vocabulary is intentionally NOT hard-coded here.
# Merchant-specific product/category terms are supplied by store_vocabulary.py
# through `store_terms`. This keeps the planner domain-agnostic.

KNOWLEDGE_WORDS = {
    "policy", "return", "refund", "shipping", "delivery", "about", "contact",
    "faq", "how", "when", "where", "office", "address", "location", "hours",
    "kothay", "thikana", "office kothay", "নীতি", "রিটার্ন", "রিফান্ড", "ডেলিভারি",
    "শিপিং", "সম্পর্কে", "যোগাযোগ", "কীভাবে", "কখন", "কোথায়", "ঠিকানা", "অফিস",
}

# These are language-level catalog-intent cues only; they contain no
# product/category vocabulary. Actual entity resolution comes from the
# merchant catalog.
CATALOG_BROWSE_CUES = {
    "কি আছে", "কী আছে", "কি কি আছে", "কী কী আছে", "সব আছে", "সব কি আছে",
    "কি পাওয়া যায়", "কী পাওয়া যায়", "ki ache", "ki ki ache", "sob ki ache",
    "shob ki ache", "sob ache", "shob ache", "ki paoa jay", "ki pawa jay",
    "what do you have", "what do you sell", "what's available", "whats available",
    "show me everything", "show all", "product list", "list of products",
    "your products", "all products", "what products", "everything you have",
}

STOP_WORDS = set(SHARED_STOPWORDS) | {
    "এমন", "যেমন", "মতো", "মত", "কম", "কমে", "নিচে", "উপরে", "বেশি",
}


def _normalize_digits(text: str) -> str:
    return text.translate(str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _normalize_price_shorthand(text: str) -> str:
    def _expand(match: re.Match, multiplier: float) -> str:
        try:
            value = float(match.group(1)) * multiplier
        except ValueError:
            return match.group(0)
        return str(int(value))

    text = re.sub(
        r"([0-9]+(?:\.[0-9]+)?)\s*k\b",
        lambda m: _expand(m, 1_000),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:hazar|hajar|হাজার)\b",
        lambda m: _expand(m, 1_000),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lac|লাখ)\b",
        lambda m: _expand(m, 100_000),
        text,
        flags=re.IGNORECASE,
    )
    return text


def _extract_max_price(text: str) -> float | None:
    text = _normalize_price_shorthand(_normalize_digits(text))
    patterns = [
        r"([0-9][0-9,]*)\s*টাকার\s*মধ্যে",
        r"([0-9][0-9,]*)\s*টাকা\s*র মধ্যে",
        r"([0-9][0-9,]*)\s*taka\s*এর মধ্যে",
        r"([0-9][0-9,]*)\s*(?:er|r)\s*(?:moddhe|modhye|modhe)",
        r"([0-9][0-9,]*)\s*টাকার\s*কমে?",
        r"([0-9][0-9,]*)\s*টাকার\s*নিচে",
        r"under\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"below\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"within\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"budget\s*(?:is|hocche|hobe)?\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*(?:max|maximum)",
        r"(?:৳|tk|taka)\s*([0-9][0-9,]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _extract_min_price(text: str) -> float | None:
    text = _normalize_price_shorthand(_normalize_digits(text))
    patterns = [
        r"(?:above|over|more than)\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*টাকার\s*উপরে",
        r"([0-9][0-9,]*)\s*টাকার\s*বেশি",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _extract_in_stock(text: str) -> bool:
    """Detect explicit availability intent, not bare existence words.

    `ase`/`ache` are ordinary Bengali/Banglish existence/copula words and
    therefore cannot be treated as stock signals by themselves. They only
    become an availability signal when the surrounding sentence has an
    availability-question structure, e.g. "mobile ase?" or
    "tomar kase ki mobile ase?". Descriptive predicates such as
    "mobile ta kemon ase?" are deliberately excluded.
    """
    normalized = _normalize_entity_text(text)
    if not normalized:
        return False

    # Explicit stock/availability terminology is unambiguous.
    explicit_patterns = [
        r"\bavailable\b",
        r"\bin\s+stock\b",
        r"\bstock\b",
        r"স্টক",
        r"স্টকে",
        r"স্টকটা",
        r"উপলব্ধ",
        r"মজুদ",
    ]
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in explicit_patterns):
        return True

    # Existence words require sentence-level availability framing.
    has_existence = bool(re.search(r"\b(?:ase|ache|আছে|আছে়|রয়েছে|রয়েছে)\b", normalized))
    if not has_existence:
        return False

    # "kemon/emon ... ase/ache" describes state/quality, not availability.
    if re.search(r"\b(?:kemon|emon|কেমন|এমন|কীভাবে|কিভাবে)\b.*\b(?:ase|ache|আছে|রয়েছে|রয়েছে)\b", normalized):
        return False

    # Availability-question constructions: "ki ... ase", "... ase?",
    # "tomar kase ki ... ase", and their Bengali/Banglish variants.
    availability_question_patterns = [
        r"\bki\b.*\b(?:ase|ache)\b",
        r"\b(?:ase|ache)\s*\??$",
        r"\b(?:আছে|রয়েছে|রয়েছে)\s*\??$",
        r"\bকী\b.*\b(?:আছে|রয়েছে|রয়েছে)\b",
        r"\bকি\b.*\b(?:আছে|রয়েছে|রয়েছে)\b",
    ]
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in availability_question_patterns):
        return True

    # A direct product/entity + existence construction ending in ase/ache
    # is naturally an availability question when phrased as a short query.
    if re.search(r"\b[\w\u0980-\u09ff.-]+\s+(?:ase|ache|আছে|রয়েছে|রয়েছে)\s*\??$", normalized):
        return True

    return False


def _clean_search_terms(
    text: str,
    exclude_words: set[str] | None = None,
    store_terms: set[str] | None = None,
) -> str:
    cleaned = text
    for pattern in [
        r"[0-9][0-9,]*\s*টাকার\s*মধ্যে",
        r"[0-9][0-9,]*\s*taka\s*এর মধ্যে",
        r"(?:under|below|within)\s*(?:৳\s*)?[0-9][0-9,]*",
        r"(?:৳|tk|taka)\s*[0-9][0-9,]*",
    ]:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    useful = []
    for token in cleaned.split():
        token = token.strip(".,!?;:()[]{}\"'“”‘’—–…")
        if not token or token.lower() in STOP_WORDS or (
            exclude_words and token.lower() in exclude_words
        ) or token.isdigit():
            continue
        useful.append(token)

    if store_terms:
        normalized_terms = {
            str(term).strip().lower()
            for term in store_terms
            if str(term).strip()
        }
        matched = [
            token for token in useful
            if token.lower() in normalized_terms
        ]
        if matched:
            return " ".join(matched)

    return " ".join(useful)


def _normalize_entity_text(value: str) -> str:
    value = _normalize_digits(value).lower().strip()
    value = re.sub(r"[^\w\u0980-\u09ff.-]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _resolve_store_entities(query: str, store_terms: set[str] | None) -> list[str]:
    if not store_terms:
        return []

    query_norm = _normalize_entity_text(query)
    if not query_norm:
        return []

    candidates = sorted(
        {
            _normalize_entity_text(str(term))
            for term in store_terms
            if str(term).strip()
        },
        key=lambda term: (len(term.split()), len(term)),
        reverse=True,
    )

    exact = []
    query_tokens = query_norm.split()

    for term in candidates:
        if not term:
            continue
        if term in query_norm:
            exact.append(term)

    if exact:
        return exact[:8]

    fuzzy = []
    for token in query_tokens:
        if len(token) < 3 or token in STOP_WORDS:
            continue
        matches = difflib.get_close_matches(
            token,
            candidates,
            n=1,
            cutoff=0.88,
        )
        if matches:
            fuzzy.append(matches[0])

    return list(dict.fromkeys(fuzzy))[:8]


def _looks_like_model_number(token: str) -> bool:
    return bool(token) and any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token)


def _catalog_browse_intent(text: str, store_entities: list[str]) -> bool:
    lowered = text.lower().strip()
    if any(cue in lowered for cue in CATALOG_BROWSE_CUES):
        return True

    generic_patterns = [
        r"\b(show|list|display)\s+(me\s+)?(all|everything)\b",
        r"\bwhat\s+(do\s+you\s+have|do\s+you\s+sell)\b",
        r"\b(all|every)\s+(items?|products?)\b",
    ]
    if any(re.search(pattern, lowered) for pattern in generic_patterns):
        return True

    return bool(store_entities) and any(
        marker in lowered
        for marker in ("সব", "কি কি", "all", "multiple", "options", "items", "products")
    )


def plan(query: str, store_terms: set[str] | None = None):
    text = query.lower()
    store_entities = _resolve_store_entities(query, store_terms)

    product_score = min(1.0, 0.55 + 0.10 * len(store_entities)) if store_entities else 0.0
    knowledge_score = sum(word in text for word in KNOWLEDGE_WORDS)

    max_price = _extract_max_price(query)
    min_price = _extract_min_price(query)
    in_stock = _extract_in_stock(query)

    search_terms = _clean_search_terms(
        query,
        store_terms=store_terms,
    )
    entity_query = " ".join(store_entities) or search_terms

    if product_score > 0 and knowledge_score > 0:
        return PlannedAction(
            intent=Intent.MIXED,
            product_filters=ProductFilters(
                product_name=entity_query or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            knowledge_query=_clean_search_terms(
                query,
                exclude_words=set(store_entities),
            ) or query,
            confidence=0.90,
        )

    if product_score > 0:
        return PlannedAction(
            intent=Intent.PRODUCT_SEARCH,
            product_filters=ProductFilters(
                product_name=entity_query or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            confidence=0.90,
        )

    if max_price is not None and search_terms:
        return PlannedAction(
            intent=Intent.PRODUCT_SEARCH,
            product_filters=ProductFilters(
                product_name=search_terms,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            confidence=0.85,
        )

    if knowledge_score > 0:
        return PlannedAction(
            intent=Intent.KNOWLEDGE_SEARCH,
            knowledge_query=query,
            confidence=0.75,
        )

    tokens = search_terms.split()
    if any(_looks_like_model_number(token) for token in tokens):
        return PlannedAction(
            intent=Intent.PRODUCT_SEARCH,
            product_filters=ProductFilters(
                product_name=search_terms or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            confidence=0.60,
        )

    if _catalog_browse_intent(query, store_entities):
        return PlannedAction(
            intent=Intent.CATALOG_BROWSE,
            confidence=0.80,
        )

    return PlannedAction(intent=Intent.UNKNOWN, confidence=0.20)
