import difflib
import re

from app.planner.models import Intent, PlannedAction, ProductFilters
from app.products.semantic_attributes import deterministic_extract
from app.search.stopwords import STOPWORDS as SHARED_STOPWORDS

KNOWLEDGE_WORDS = {
    "policy", "return", "refund", "shipping", "delivery", "about", "contact",
    "faq", "how", "when", "where", "office", "address", "location", "hours",
    "kothay", "thikana", "office kothay", "নীতি", "রিটার্ন", "রিফান্ড", "ডেলিভারি",
    "শিপিং", "সম্পর্কে", "যোগাযোগ", "কীভাবে", "কখন", "কোথায়", "ঠিকানা", "অফিস",
}
CATALOG_BROWSE_CUES = {
    "কি আছে", "কী আছে", "কি কি আছে", "কী কী আছে", "সব আছে", "সব কি আছে",
    "কি পাওয়া যায়", "কী পাওয়া যায়", "ki ache", "ki ki ache", "sob ki ache",
    "shob ki ache", "sob ache", "shob ache", "ki paoa jay", "ki pawa jay",
    "what do you have", "what do you sell", "what's available", "whats available",
    "show me everything", "show all", "product list", "list of products",
    "your products", "all products", "what products", "everything you have",
}
RECOMMENDATION_CUES = {
    "best", "top", "recommend", "recommended", "suggest", "suggestion",
    "সেরা", "সর্বোত্তম", "ভালো", "ভাল", "সাজেস্ট", "রিকমেন্ড", "সবচেয়ে ভালো", "সবচেয়ে ভালো",
}
STOP_WORDS = set(SHARED_STOPWORDS) | {"এমন", "যেমন", "মতো", "মত", "কম", "কমে", "নিচে", "উপরে", "বেশি"}


def _normalize_digits(text: str) -> str:
    return text.translate(str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _normalize_price_shorthand(text: str) -> str:
    def _expand(match: re.Match, multiplier: float) -> str:
        try: value = float(match.group(1)) * multiplier
        except ValueError: return match.group(0)
        return str(int(value))
    text = re.sub(r"([0-9]+(?:\.[0-9]+)?)\s*k\b", lambda m: _expand(m, 1_000), text, flags=re.IGNORECASE)
    text = re.sub(r"([0-9]+(?:\.[0-9]+)?)\s*(?:hazar|hajar|হাজার)\b", lambda m: _expand(m, 1_000), text, flags=re.IGNORECASE)
    text = re.sub(r"([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lac|লাখ)\b", lambda m: _expand(m, 100_000), text, flags=re.IGNORECASE)
    return text


def _extract_max_price(text: str) -> float | None:
    text = _normalize_price_shorthand(_normalize_digits(text))
    patterns = [r"([0-9][0-9,]*)\s*টাকার\s*মধ্যে", r"([0-9][0-9,]*)\s*টাকা\s*র মধ্যে", r"([0-9][0-9,]*)\s*taka\s*এর মধ্যে", r"([0-9][0-9,]*)\s*(?:er|r)\s*(?:moddhe|modhye|modhe)", r"([0-9][0-9,]*)\s*টাকার\s*কমে?", r"([0-9][0-9,]*)\s*টাকার\s*নিচে", r"under\s*(?:৳\s*)?([0-9][0-9,]*)", r"below\s*(?:৳\s*)?([0-9][0-9,]*)", r"within\s*(?:৳\s*)?([0-9][0-9,]*)", r"budget\s*(?:is|hocche|hobe)?\s*(?:৳\s*)?([0-9][0-9,]*)", r"([0-9][0-9,]*)\s*(?:max|maximum)", r"(?:৳|tk|taka)\s*([0-9][0-9,]*)"]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try: return float(match.group(1).replace(",", ""))
            except ValueError: pass
    return None


def _extract_min_price(text: str) -> float | None:
    text = _normalize_price_shorthand(_normalize_digits(text))
    patterns = [r"(?:above|over|more than)\s*(?:৳\s*)?([0-9][0-9,]*)", r"([0-9][0-9,]*)\s*টাকার\s*উপরে", r"([0-9][0-9,]*)\s*টাকার\s*বেশি"]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try: return float(match.group(1).replace(",", ""))
            except ValueError: pass
    return None


def _normalize_entity_text(value: str) -> str:
    value = _normalize_digits(value).lower().strip()
    value = re.sub(r"[^\w\u0980-\u09ff.-]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _compact_entity(value: str) -> str:
    return re.sub(r"[^a-z0-9\u0980-\u09ff]+", "", _normalize_entity_text(value))


def _extract_in_stock(text: str) -> bool:
    normalized = _normalize_entity_text(text)
    if not normalized: return False
    explicit_patterns = [r"\bavailable\b", r"\bin\s+stock\b", r"\bstock\b", r"স্টক", r"স্টকে", r"স্টকটা", r"উপলব্ধ", r"মজুদ"]
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in explicit_patterns): return True
    has_existence = bool(re.search(r"\b(?:ase|ache|আছে|আছে়|রয়েছে|রয়েছে)\b", normalized))
    if not has_existence: return False
    if re.search(r"\b(?:kemon|emon|কেমন|এমন|কীভাবে|কিভাবে)\b.*\b(?:ase|ache|আছে|রয়েছে|রয়েছে)\b", normalized): return False
    availability_question_patterns = [r"\bki\b.*\b(?:ase|ache)\b", r"\b(?:ase|ache)\s*\??$", r"\b(?:আছে|রয়েছে|রয়েছে)\s*\??$", r"\bকী\b.*\b(?:আছে|রয়েছে|রয়েছে)\b", r"\bকি\b.*\b(?:আছে|রয়েছে|রয়েছে)\b"]
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in availability_question_patterns): return True
    return bool(re.search(r"\b[\w\u0980-\u09ff.-]+\s+(?:ase|ache|আছে|রয়েছে|রয়েছে)\s*\??$", normalized))


def _clean_search_terms(text: str, exclude_words: set[str] | None = None, store_terms: set[str] | None = None) -> str:
    cleaned = text
    for pattern in [r"[0-9][0-9,]*\s*টাকার\s*মধ্যে", r"[0-9][0-9,]*\s*taka\s*এর মধ্যে", r"(?:under|below|within)\s*(?:৳\s*)?[0-9][0-9,]*", r"(?:৳|tk|taka)\s*[0-9][0-9,]*"]:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    useful = []
    for token in cleaned.split():
        token = token.strip(".,!?;:()[]{}\"'“”‘’—–…")
        if not token or token.lower() in STOP_WORDS or (exclude_words and token.lower() in exclude_words) or token.isdigit(): continue
        useful.append(token)
    if store_terms:
        normalized_terms = {str(term).strip().lower() for term in store_terms if str(term).strip()}
        matched = [token for token in useful if token.lower() in normalized_terms]
        if matched: return " ".join(matched)
    return " ".join(useful)


def _resolve_store_entities(query: str, store_terms: set[str] | None) -> list[str]:
    if not store_terms: return []
    query_norm = _normalize_entity_text(query)
    if not query_norm: return []
    candidates = sorted({_normalize_entity_text(str(term)) for term in store_terms if str(term).strip()}, key=lambda term: (len(term.split()), len(term)), reverse=True)
    exact = [term for term in candidates if term and term in query_norm]
    if exact: return exact[:8]
    compact_query = _compact_entity(query_norm)
    compact_candidates = [(term, _compact_entity(term)) for term in candidates]
    compact_exact = [term for term, compact in compact_candidates if compact and compact in compact_query]
    if compact_exact: return compact_exact[:8]
    query_tokens = [t for t in query_norm.split() if len(t) >= 3 and t not in STOP_WORDS]
    substring_matches = []
    for token in query_tokens:
        compact_token = _compact_entity(token)
        if len(compact_token) < 3: continue
        for term, compact in compact_candidates:
            if compact_token in compact or compact in compact_token:
                substring_matches.append(term)
    if substring_matches: return list(dict.fromkeys(substring_matches))[:8]
    fuzzy = []
    for token in query_tokens:
        matches = difflib.get_close_matches(token, candidates, n=1, cutoff=0.82)
        if matches: fuzzy.append(matches[0])
    return list(dict.fromkeys(fuzzy))[:8]


def _looks_like_model_number(token: str) -> bool:
    return bool(token) and any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token)


def _catalog_browse_intent(text: str, store_entities: list[str]) -> bool:
    lowered = text.lower().strip()
    if any(cue in lowered for cue in CATALOG_BROWSE_CUES): return True
    if any(re.search(pattern, lowered) for pattern in [r"\b(show|list|display)\s+(me\s+)?(all|everything)\b", r"\bwhat\s+(do\s+you\s+have|do\s+you\s+sell)\b", r"\b(all|every)\s+(items?|products?)\b"]): return True
    return bool(store_entities) and any(marker in lowered for marker in ("সব", "কি কি", "all", "multiple", "options", "items", "products"))


def _extract_attributes(query: str, store_terms):
    schema = getattr(store_terms, "attribute_schema", None) or {}
    return deterministic_extract(query, schema) if schema else {}


def _attribute_search_exclusions(attributes: dict, store_terms=None) -> set[str]:
    excluded = set()
    schema = getattr(store_terms, "attribute_schema", None) or {}
    for aliases in schema.values():
        for alias in aliases: excluded.update(_normalize_entity_text(alias).split())
    for value in attributes.values():
        if isinstance(value, str): excluded.update(_normalize_entity_text(value).split())
    return excluded


def _is_recommendation_query(text: str) -> bool:
    lowered = text.casefold()
    return any(cue in lowered for cue in RECOMMENDATION_CUES) or "best seller" in lowered or "best-seller" in lowered


def plan(query: str, store_terms: set[str] | None = None):
    text = query.lower()
    attributes = _extract_attributes(query, store_terms)
    attribute_exclusions = _attribute_search_exclusions(attributes, store_terms)
    schema = getattr(store_terms, "attribute_schema", None) or {}
    store_entities = [entity for entity in _resolve_store_entities(query, store_terms) if entity not in attribute_exclusions and not any(entity in aliases for aliases in schema.values())]
    recommendation = _is_recommendation_query(query)
    product_score = min(1.0, 0.55 + 0.10 * len(store_entities)) if store_entities else (0.70 if attributes else (0.65 if recommendation else 0.0))
    knowledge_score = sum(word in text for word in KNOWLEDGE_WORDS)
    max_price = _extract_max_price(query)
    min_price = _extract_min_price(query)
    in_stock = _extract_in_stock(query)
    search_terms = _clean_search_terms(query, exclude_words=attribute_exclusions, store_terms=store_terms)
    entity_query = " ".join(store_entities) or search_terms
    if recommendation and not store_entities: entity_query = None
    common_filters = dict(product_name=entity_query or None, min_price=min_price, max_price=max_price, in_stock=in_stock, recommendation=recommendation, attributes=attributes)
    if product_score > 0 and knowledge_score > 0:
        return PlannedAction(intent=Intent.MIXED, product_filters=ProductFilters(**common_filters), knowledge_query=_clean_search_terms(query, exclude_words=set(store_entities) | attribute_exclusions) or query, confidence=0.90)
    if recommendation:
        return PlannedAction(intent=Intent.RECOMMENDATION, product_filters=ProductFilters(**common_filters), confidence=0.92 if store_entities else 0.80)
    if product_score > 0:
        return PlannedAction(intent=Intent.PRODUCT_SEARCH, product_filters=ProductFilters(**common_filters), confidence=0.90)
    if max_price is not None and search_terms:
        return PlannedAction(intent=Intent.PRODUCT_SEARCH, product_filters=ProductFilters(product_name=search_terms, min_price=min_price, max_price=max_price, in_stock=in_stock, attributes=attributes), confidence=0.85)
    if knowledge_score > 0:
        return PlannedAction(intent=Intent.KNOWLEDGE_SEARCH, knowledge_query=query, confidence=0.75)
    tokens = search_terms.split()
    if any(_looks_like_model_number(token) for token in tokens):
        return PlannedAction(intent=Intent.PRODUCT_SEARCH, product_filters=ProductFilters(product_name=search_terms or None, min_price=min_price, max_price=max_price, in_stock=in_stock, attributes=attributes), confidence=0.60)
    if _catalog_browse_intent(query, store_entities): return PlannedAction(intent=Intent.CATALOG_BROWSE, confidence=0.80)
    return PlannedAction(intent=Intent.UNKNOWN, confidence=0.20)
