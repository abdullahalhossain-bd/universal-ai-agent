import re

from app.planner.models import Intent, PlannedAction, ProductFilters
from app.search.stopwords import STOPWORDS as SHARED_STOPWORDS

PRODUCT_WORDS = {
    "product", "products", "shoe", "shoes", "shirt", "shirts", "phone", "smartphone", "iphone", "mobile", "laptop", "notebook", "computer", "pc", "desktop", "mouse", "keyboard", "monitor", "printer", "scanner", "charger", "adapter", "cable", "speaker", "headphone", "headset", "earphone", "earbud", "camera", "webcam", "router", "modem", "pendrive", "flash drive", "hard drive", "ssd", "ram", "power bank", "ups", "cpu", "processor", "graphics card", "motherboard", "cooler", "watch", "bag", "dress", "জুতা", "জুতো", "জামা", "শার্ট", "মোবাইল", "ফোন", "ল্যাপটপ", "কম্পিউটার", "মাউস", "কীবোর্ড", "মনিটর", "প্রিন্টার", "চার্জার", "হেডফোন", "ইয়ারফোন", "স্পিকার", "ক্যামেরা", "রাউটার", "পাওয়ার ব্যাংক", "ঘড়ি", "ব্যাগ", "ড্রেস",
}

KNOWLEDGE_WORDS = {"policy", "return", "refund", "shipping", "delivery", "about", "contact", "faq", "how", "when", "where", "office", "address", "location", "hours", "kothay", "thikana", "office kothay", "নীতি", "রিটার্ন", "রিফান্ড", "ডেলিভারি", "শিপিং", "সম্পর্কে", "যোগাযোগ", "কীভাবে", "কখন", "কোথায়", "ঠিকানা", "অফিস"}

# Generic "what do you sell / show me everything" phrases — no specific
# product word, so PRODUCT_WORDS/store_terms scoring finds nothing and
# these used to fall all the way through to Intent.UNKNOWN's plain
# greeting reply. Checked only when nothing more specific already
# matched (see plan()), so it never overrides a real product/knowledge
# query.
CATALOG_BROWSE_PHRASES = {
    "কি আছে", "কী আছে", "কি কি আছে", "কী কী আছে", "সব আছে", "সব কি আছে",
    "সব পণ্য", "সব প্রোডাক্ট", "কি পাওয়া যায়", "কী পাওয়া যায়",
    "ki ache", "ki asche", "ki ki ache", "ki ki asche", "kimon product ache",
    "sob ki ache", "shob ki ache", "sob product", "shob product",
    "sob ache", "shob ache", "ki paoa jay", "ki pawa jay",
    "what do you have", "what do you sell", "what's available",
    "whats available", "show me everything", "show all products",
    "show all", "product list", "list of products", "your products",
    "all products", "what products", "everything you have",
}

# Keep planner-local terms for backward compatibility, but inherit the
# shared query vocabulary so planner and SQL search cannot disagree.
STOP_WORDS = set(SHARED_STOPWORDS) | {
    "এমন", "যেমন", "মতো", "মত", "কম", "কমে", "নিচে", "উপরে", "বেশি",
}


def _normalize_digits(text: str) -> str:
    return text.translate(str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _normalize_price_shorthand(text: str) -> str:
    # "20k" / "20 hazar" / "২০ হাজার" all mean 20,000 — expand these to
    # a plain number *before* the patterns below run, instead of
    # hand-adding a parallel regex for every shorthand a customer might
    # type ("20k", "20k budget", "budget 20k", "20 hajar" ...). New
    # shorthand only needs a new multiplier entry here, not a new
    # price-pattern per phrasing.
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
    return any(word in lowered for word in {
        "available", "in stock", "stock আছে", "স্টকে আছে", "স্টক আছে",
        "available আছে", "stock ase", "stock ache", "available ase",
        "available ache", "ase", "ache",
    })


def _clean_search_terms(text: str, exclude_words: set[str] | None = None) -> str:
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
        if not token or token.lower() in STOP_WORDS or (exclude_words and token.lower() in exclude_words) or token.isdigit():
            continue
        useful.append(token)
    return " ".join(useful)


def _looks_like_model_number(token: str) -> bool:
    return bool(token) and any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token)


def plan(query: str, store_terms: set[str] | None = None):
    text = query.lower()
    product_score = sum(word in text for word in PRODUCT_WORDS)
    if store_terms:
        product_score += sum(term.lower() in text for term in store_terms)
    knowledge_score = sum(word in text for word in KNOWLEDGE_WORDS)
    max_price = _extract_max_price(query)
    min_price = _extract_min_price(query)
    in_stock = _extract_in_stock(query)
    search_terms = _clean_search_terms(query)

    if product_score > 0 and knowledge_score > 0:
        return PlannedAction(intent=Intent.MIXED, product_filters=ProductFilters(product_name=_clean_search_terms(query, KNOWLEDGE_WORDS) or None, min_price=min_price, max_price=max_price, in_stock=in_stock), knowledge_query=_clean_search_terms(query, PRODUCT_WORDS) or query, confidence=0.90)
    if product_score > 0:
        return PlannedAction(intent=Intent.PRODUCT_SEARCH, product_filters=ProductFilters(product_name=search_terms or None, min_price=min_price, max_price=max_price, in_stock=in_stock), confidence=0.90)
    if max_price is not None and search_terms:
        return PlannedAction(intent=Intent.PRODUCT_SEARCH, product_filters=ProductFilters(product_name=search_terms, min_price=min_price, max_price=max_price, in_stock=in_stock), confidence=0.85)
    if knowledge_score > 0:
        return PlannedAction(intent=Intent.KNOWLEDGE_SEARCH, knowledge_query=query, confidence=0.75)
    tokens = search_terms.split()
    if any(_looks_like_model_number(token) for token in tokens):
        return PlannedAction(intent=Intent.PRODUCT_SEARCH, product_filters=ProductFilters(product_name=search_terms or None, min_price=min_price, max_price=max_price, in_stock=in_stock), confidence=0.60)
    if any(phrase in text for phrase in CATALOG_BROWSE_PHRASES):
        return PlannedAction(intent=Intent.CATALOG_BROWSE, confidence=0.80)
    return PlannedAction(intent=Intent.UNKNOWN, confidence=0.20)