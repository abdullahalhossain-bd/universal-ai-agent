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
    lowered = text.lower()
    # Do not treat generic Bengali/Banglish existence words such as
    # "ase"/"ache" as stock filters. They are ordinary language and are
    # already handled by the shared stopword vocabulary.
    explicit_phrases = {
        "available", "in stock", "stock আছে", "স্টকে আছে", "স্টক আছে",
        "available আছে", "stock ase", "stock ache", "available ase",
        "available ache",
    }
    return any(phrase in lowered for phrase in explicit_phrases)


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

    # When merchant vocabulary is available, prefer actual catalog entities
    # over arbitrary query words. This is the key boundary between generic
    # language and merchant-specific search semantics.
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
    """Resolve query text against the merchant's live catalog vocabulary.

    Matching is deliberately domain-agnostic:
    - exact multi-word catalog terms first
    - token/phrase containment next
    - conservative fuzzy matching for typos/transliterations

    No product type (laptop/phone/shoe/etc.) is assumed by the planner.
    """
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

    # Conservative fuzzy matching: only compare meaningful query tokens
    # and only accept a strong similarity. This helps "samsng" -> "samsung"
    # without turning arbitrary customer language into a product entity.
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

    # Generic requests such as "show me all", "what's available" or
    # equivalent language can be recognized without knowing any product type.
    generic_patterns = [
        r"\b(show|list|display)\s+(me\s+)?(all|everything)\b",
        r"\bwhat\s+(do\s+you\s+have|do\s+you\s+sell)\b",
        r"\b(all|every)\s+(items?|products?)\b",
    ]
    if any(re.search(pattern, lowered) for pattern in generic_patterns):
        return True

    # If the query resolves to a merchant entity and asks for plural/multiple
    # items, the catalog itself determines what is being browsed.
    return bool(store_entities) and any(
        marker in lowered
        for marker in ("সব", "কি কি", "all", "multiple", "options", "items", "products")
    )


def plan(query: str, store_terms: set[str] | None = None):
    text = query.lower()
    store_entities = _resolve_store_entities(query, store_terms)

    # Merchant vocabulary is the primary product signal. Hard-coded product
    # categories are intentionally absent, so any merchant can be supported.
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

    # Unknown/domain-new language is intentionally left low-confidence so a
    # semantic LLM planner can handle it instead of guessing from a static
    # product dictionary.
    return PlannedAction(intent=Intent.UNKNOWN, confidence=0.20)
