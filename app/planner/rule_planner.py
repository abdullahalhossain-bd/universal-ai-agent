import re

from app.planner.models import Intent, PlannedAction, ProductFilters


PRODUCT_WORDS = {
    "product", "products", "shoe", "shoes", "shirt", "shirts", "phone",
    "smartphone", "iphone", "mobile", "laptop", "notebook", "computer", "pc",
    "desktop", "mouse", "keyboard", "monitor", "printer", "scanner", "charger",
    "adapter", "cable", "speaker", "headphone", "headset", "earphone", "earbud",
    "camera", "webcam", "router", "modem", "pendrive", "flash drive", "hard drive",
    "ssd", "ram", "power bank", "ups", "cpu", "processor", "graphics card",
    "motherboard", "cooler", "watch", "bag", "dress", "জুতা", "জুতো", "জামা",
    "শার্ট", "মোবাইল", "ফোন", "ল্যাপটপ", "কম্পিউটার", "মাউস", "কীবোর্ড", "মনিটর",
    "প্রিন্টার", "চার্জার", "হেডফোন", "ইয়ারফোন", "স্পিকার", "ক্যামেরা", "রাউটার",
    "পাওয়ার ব্যাংক", "ঘড়ি", "ব্যাগ", "ড্রেস",
}

KNOWLEDGE_WORDS = {
    "policy", "return", "refund", "shipping", "delivery", "about", "contact",
    "faq", "how", "when", "নীতি", "রিটার্ন", "রিফান্ড", "ডেলিভারি", "শিপিং",
    "সম্পর্কে", "যোগাযোগ", "কীভাবে", "কখন",
}

STOP_WORDS = {
    "show", "find", "me", "please", "available", "in", "stock", "under", "below",
    "within", "price", "টাকার", "টাকা", "মধ্যে", "জন্য", "দেখাও", "দেখান", "চাই",
    "আছে", "স্টকে", "স্টক", "এর", "ও", "আর", "এবং", "and", "কী", "কি", "এমন",
    "যেমন", "মতো", "মত", "কম", "কমে", "নিচে", "উপরে", "বেশি", "the", "a", "an",
    "of", "for", "to", "with", "is", "are", "my", "get", "give", "want",
}

NON_PRODUCT_WORDS = {
    "hi", "hello", "hey", "thanks", "thank", "ok", "okay", "হাই", "হ্যালো", "ধন্যবাদ",
}


def _normalize_digits(text: str) -> str:
    translation = str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return text.translate(translation)


def _number(patterns, text):
    text = _normalize_digits(text)
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _extract_max_price(text: str) -> float | None:
    return _number([
        r"([0-9][0-9,]*)\s*টাকার\s*মধ্যে",
        r"([0-9][0-9,]*)\s*টাকা\s*র মধ্যে",
        r"([0-9][0-9,]*)\s*taka\s*এর মধ্যে",
        r"([0-9][0-9,]*)\s*টাকার\s*কমে?",
        r"([0-9][0-9,]*)\s*টাকার\s*নিচে",
        r"under\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"below\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"within\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"(?:৳|tk|taka)\s*([0-9][0-9,]*)",
    ], text)


def _extract_min_price(text: str) -> float | None:
    return _number([
        r"(?:above|over|more than)\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*টাকার\s*উপরে",
        r"([0-9][0-9,]*)\s*টাকার\s*বেশি",
    ], text)


def _extract_in_stock(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in {
        "available", "in stock", "stock আছে", "স্টকে আছে", "স্টক আছে", "available আছে",
    })


def _clean_search_terms(text: str, exclude_words: set[str] | None = None) -> str:
    cleaned = _normalize_digits(text)
    cleaned = re.sub(r"[0-9][0-9,]*\s*টাকার\s*মধ্যে", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"[0-9][0-9,]*\s*taka\s*এর মধ্যে", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:under|below|within)\s*(?:৳\s*)?[0-9][0-9,]*", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:৳|tk|taka)\s*[0-9][0-9,]*", " ", cleaned, flags=re.I)

    useful = []
    excluded = {w.lower() for w in (exclude_words or set())}
    for token in cleaned.split():
        token = token.strip(".,!?;:()[]{}\"'")
        if not token or token.lower() in STOP_WORDS or token.lower() in excluded:
            continue
        if token.isdigit() or len(token) < 2:
            continue
        useful.append(token)
    return " ".join(useful)


def plan(query: str):
    text = (query or "").strip()
    lowered = text.lower()
    product_score = sum(word in lowered for word in PRODUCT_WORDS)
    knowledge_score = sum(word in lowered for word in KNOWLEDGE_WORDS)
    max_price = _extract_max_price(text)
    min_price = _extract_min_price(text)
    in_stock = _extract_in_stock(text)
    search_terms = _clean_search_terms(text)

    if product_score > 0 and knowledge_score > 0:
        return PlannedAction(
            intent=Intent.MIXED,
            product_filters=ProductFilters(
                product_name=_clean_search_terms(text, KNOWLEDGE_WORDS) or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            knowledge_query=_clean_search_terms(text, PRODUCT_WORDS) or text,
            confidence=0.90,
        )

    if product_score > 0:
        return PlannedAction(
            intent=Intent.PRODUCT_SEARCH,
            product_filters=ProductFilters(
                product_name=search_terms or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            confidence=0.90,
        )

    if knowledge_score > 0:
        return PlannedAction(
            intent=Intent.KNOWLEDGE_SEARCH,
            knowledge_query=text,
            confidence=0.75,
        )

    # Generic product fallback: product names/categories/brands are merchant
    # data, so the planner must not maintain a hard-coded product vocabulary.
    # This is what makes "Acme X200", "summer collection", or an unknown
    # merchant-specific category eligible for DB-backed product search.
    if search_terms and lowered not in NON_PRODUCT_WORDS:
        return PlannedAction(
            intent=Intent.PRODUCT_SEARCH,
            product_filters=ProductFilters(
                product_name=search_terms,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            confidence=0.70,
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
            confidence=0.70,
        )

    return PlannedAction(intent=Intent.UNKNOWN, confidence=0.20)
