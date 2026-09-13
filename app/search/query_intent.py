"""Deterministic ecommerce intent extraction used as a safe planner fallback."""

import re

from app.search.synonyms import SEARCH_SYNONYMS

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_STOPWORDS = {
    "er", "এর", "ache", "আছে", "show", "দেখাও", "dekhao", "please", "plz",
    "the", "a", "an", "for", "under", "within", "below", "below", "tk", "taka",
    "টাকা", "দাম", "price", "products", "product", "পণ্য", "দাও", "চাই", "কি", "কী",
}
_PRICE_WORDS = {"tk", "taka", "টাকা", "bdt", "৳", "দাম", "price"}
_CATEGORY_GROUPS = {
    "category": {
        "জুতা", "shoe", "shoes", "footwear", "স্যান্ডেল", "sandal", "sandals",
        "slipper", "slippers", "শার্ট", "shirt", "shirts", "প্যান্ট", "pant", "pants",
        "trouser", "trousers", "টি-শার্ট", "t-shirt", "tshirt", "tee", "ব্যাগ", "bag",
        "bags", "handbag", "backpack", "মোবাইল", "mobile", "phone", "smartphone",
        "ল্যাপটপ", "laptop", "notebook", "হেডফোন", "headphone", "headphones", "earbuds",
        "চার্জার", "charger", "adapter", "ক্যামেরা", "camera", "ফ্রিজ", "fridge",
        "refrigerator", "পারফিউম", "perfume", "fragrance", "সাবান", "soap", "শ্যাম্পু", "shampoo",
    },
    "color": {
        "কালো": "black", "black": "black", "সাদা": "white", "white": "white",
        "লাল": "red", "red": "red", "নীল": "blue", "blue": "blue", "সবুজ": "green",
        "green": "green", "হলুদ": "yellow", "yellow": "yellow", "গোলাপি": "pink",
        "pink": "pink", "ধূসর": "gray", "gray": "gray", "grey": "gray",
        "বাদামী": "brown", "brown": "brown", "বেগুনি": "purple", "purple": "purple",
        "violet": "purple",
    },
}


def _number(text: str) -> float | None:
    try:
        return float(text.translate(_BN_DIGITS).replace(",", ""))
    except (TypeError, ValueError):
        return None


def extract_product_intent(query: str) -> dict:
    """Extract safe high-signal filters while preserving unknown text."""
    text = str(query or "").strip()
    lowered = text.lower()
    filters: dict = {}
    consumed: set[str] = set()

    # Price expressions: 3000 টাকা, ৳3000, 3000 tk, under 3000, <= 3000.
    price_patterns = [
        (r"(?:under|below|within|up\s*to|upto|<=)\s*[৳]?\s*([0-9০-৯][0-9০-৯,]*(?:\.[0-9]+)?)", "max_price"),
        (r"[৳]?\s*([0-9০-৯][0-9০-৯,]*(?:\.[0-9]+)?)\s*(?:tk|taka|টাকা|bdt)\b", "max_price"),
        (r"(?:দাম|price)\s*(?:<=|under|below|এর মধ্যে|মধ্যে)\s*[৳]?\s*([0-9০-৯][0-9০-৯,]*)", "max_price"),
    ]
    for pattern, target in price_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            value = _number(match.group(1))
            if value is not None:
                filters[target] = value
                consumed.add(match.group(0))
                break

    tokens = re.findall(r"[\wÀ-ÿঀ-৿]+(?:-[\wÀ-ÿঀ-৿]+)*", lowered, flags=re.UNICODE)

    # Category and color are backed by the shared synonym vocabulary.
    category = next((token for token in tokens if token in _CATEGORY_GROUPS["category"]), None)
    if category:
        category_synonyms = SEARCH_SYNONYMS.get(category)
        if category_synonyms:
            canonical = category_synonyms[0]
            filters["category"] = canonical if canonical not in {"জুতা", "shoe"} else "shoe"
        else:
            filters["category"] = category
        consumed.add(category)

    color = next((token for token in tokens if token in _CATEGORY_GROUPS["color"]), None)
    if color:
        filters["color"] = _CATEGORY_GROUPS["color"][color]
        consumed.add(color)

    # Brand is deliberately conservative: choose an unknown ASCII token rather
    # than guessing from Bengali stopwords, price terms, or known attributes.
    known_terms = set(_STOPWORDS) | set(_CATEGORY_GROUPS["category"]) | set(_CATEGORY_GROUPS["color"])
    known_terms |= {s.lower() for group in SEARCH_SYNONYMS.values() for s in group}
    known_terms |= _PRICE_WORDS
    for token in tokens:
        if token in known_terms or token.isdigit() or len(token) < 2:
            continue
        if re.fullmatch(r"[a-z][a-z0-9&._-]*", token):
            filters.setdefault("brand", token.title())
            consumed.add(token)
            break

    if any(word in lowered for word in ("ache", "আছে", "available", "in stock", "stock", "মজুদ", "স্টক")):
        filters["in_stock_only"] = True

    # Remove recognized intent words so SQL does not AND on conversational glue.
    residual = lowered
    for phrase in sorted(consumed, key=len, reverse=True):
        residual = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", residual)
    residual_tokens = [t for t in re.findall(r"[\wÀ-ÿঀ-৿]+(?:-[\wÀ-ÿঀ-৿]+)*", residual, flags=re.UNICODE) if t not in _STOPWORDS]

    return {
        "query": " ".join(residual_tokens) or None,
        "product_name": None,
        **filters,
    }
