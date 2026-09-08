import re

from app.planner.models import Intent, PlannedAction, ProductFilters

PRODUCT_WORDS = {
    "product", "products", "shoe", "shoes", "shirt", "shirts", "phone", "smartphone", "iphone", "mobile", "laptop", "notebook", "computer", "pc", "desktop", "mouse", "keyboard", "monitor", "printer", "scanner", "charger", "adapter", "cable", "speaker", "headphone", "headset", "earphone", "earbud", "camera", "webcam", "router", "modem", "pendrive", "flash drive", "hard drive", "ssd", "ram", "power bank", "ups", "cpu", "processor", "graphics card", "motherboard", "cooler", "watch", "bag", "dress", "জুতা", "জুতো", "জামা", "শার্ট", "মোবাইল", "ফোন", "ল্যাপটপ", "কম্পিউটার", "মাউস", "কীবোর্ড", "মনিটর", "প্রিন্টার", "চার্জার", "হেডফোন", "ইয়ারফোন", "স্পিকার", "ক্যামেরা", "রাউটার", "পাওয়ার ব্যাংক", "ঘড়ি", "ব্যাগ", "ড্রেস",
}

KNOWLEDGE_WORDS = {"policy", "return", "refund", "shipping", "delivery", "about", "contact", "faq", "how", "when", "নীতি", "রিটার্ন", "রিফান্ড", "ডেলিভারি", "শিপিং", "সম্পর্কে", "যোগাযোগ", "কীভাবে", "কখন"}

STOP_WORDS = {
    "show", "find", "me", "please", "available", "in", "stock", "under", "below", "within", "price", "টাকার", "টাকা", "মধ্যে", "জন্য", "দেখাও", "দেখান", "চাই", "আছে", "স্টকে", "স্টক", "এর", "ও", "আর", "এবং", "and", "কী", "কি", "এমন", "যেমন", "মতো", "মত", "কম", "কমে", "নিচে", "উপরে", "বেশি", "ase", "ache", "asche", "asha", "chai", "dekhao", "dekhan", "stoke",
}


def _normalize_digits(text: str) -> str:
    return text.translate(str.maketrans("০১২৩৪৫৬৭৮৯٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _extract_max_price(text: str) -> float | None:
    text = _normalize_digits(text)
    patterns = [r"([0-9][0-9,]*)\s*টাকার\s*মধ্যে", r"([0-9][0-9,]*)\s*টাকা\s*র মধ্যে", r"([0-9][0-9,]*)\s*taka\s*এর মধ্যে", r"([0-9][0-9,]*)\s*টাকার\s*কমে?", r"([0-9][0-9,]*)\s*টাকার\s*নিচে", r"under\s*(?:৳\s*)?([0-9][0-9,]*)", r"below\s*(?:৳\s*)?([0-9][0-9,]*)", r"within\s*(?:৳\s*)?([0-9][0-9,]*)", r"(?:৳|tk|taka)\s*([0-9][0-9,]*)"]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _extract_min_price(text: str) -> float | None:
    text = _normalize_digits(text)
    patterns = [r"(?:above|over|more than)\s*(?:৳\s*)?([0-9][0-9,]*)", r"([0-9][0-9,]*)\s*টাকার\s*উপরে", r"([0-9][0-9,]*)\s*টাকার\s*বেশি"]
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
    return any(word in lowered for word in {"available", "in stock", "stock আছে", "স্টকে আছে", "স্টক আছে", "available আছে", "stock ase", "stock ache", "available ase", "available ache", "ase", "ache"})


def _clean_search_terms(text: str, exclude_words: set[str] | None = None) -> str:
    cleaned = text
    for pattern in [r"[0-9][0-9,]*\s*টাকার\s*মধ্যে", r"[0-9][0-9,]*\s*taka\s*এর মধ্যে", r"(?:under|below|within)\s*(?:৳\s*)?[0-9][0-9,]*", r"(?:৳|tk|taka)\s*[0-9][0-9,]*"]:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    useful = []
    for token in cleaned.split():
        token = token.strip(".,!?;:()[]{}\"'")
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
        product_score += sum(term in text for term in store_terms)
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
    return PlannedAction(intent=Intent.UNKNOWN, confidence=0.20)
