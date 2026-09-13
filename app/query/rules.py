import re


PRICE_PATTERN = re.compile(
    r"(?:৳|টাকা|taka|tk)\s*([0-9,]+)",
    re.IGNORECASE,
)

# Words that describe the request rather than the catalog item.  Keeping this
# list generic makes extraction work for any merchant catalog.
_QUERY_STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "did", "have", "has",
    "what", "which", "where", "show", "find", "search", "give", "please",
    "me", "for", "of", "in", "on", "under", "below", "less", "than", "within",
    "available", "availability", "stock", "stocks", "product", "products",
    "ki", "kI", "kita", "kiita", "ki ki", "sob", "shob", "ase", "ache", "ache?",
    "ache", "nei", "nai", "lagbe", "chai", "den", "dao", "dekhao", "dekhan",
    "দাম", "মূল্য", "কত", "টাকা", "মধ্যে", "এর", "জন্য", "আছে", "আসছে", "স্টক",
    "স্টকে", "পণ্য", "প্রোডাক্ট", "দেখাও", "দেখান", "খুঁজে", "দেন", "দাও", "কি", "কী",
    "কি কি", "কী কী", "সব", "শব", "নেই", "নাই",
}


def extract_max_price(text: str) -> float | None:
    patterns = [
        r"([0-9,]+)\s*টাকার মধ্যে",
        r"([0-9,]+)\s*taka\s*এর মধ্যে",
        r"under\s*([0-9,]+)",
        r"below\s*([0-9,]+)",
        r"less than\s*([0-9,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def wants_in_stock(text: str) -> bool | None:
    text = text.casefold()
    negative = ["out of stock", "স্টক নেই", "স্টক নাই", "নেই", "nai", "nei"]
    positive = [
        "available", "in stock", "স্টকে", "স্টক আছে", "available আছে",
        "আছে", "ache", "ase", "অ্যাভেইলেবল",
    ]
    if any(x in text for x in negative):
        return False
    if any(x in text for x in positive):
        return True
    return None


def extract_search_terms(text: str) -> list[str]:
    """Extract catalog terms without hard-coding merchant product names."""
    normalized = text.casefold().strip()
    normalized = re.sub(r"[৳,]", " ", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", " ", normalized)
    tokens = re.findall(r"[a-z0-9]+|[\u0980-\u09ff]+", normalized)
    terms: list[str] = []
    for token in tokens:
        if len(token) < 2 or token in _QUERY_STOPWORDS:
            continue
        if token in {"taka", "tk", "under", "below", "less", "than"}:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:8]


def detect_intent(text: str) -> str:
    text_lower = text.casefold().strip()
    terms = extract_search_terms(text_lower)

    if any(x in text_lower for x in ["order", "অর্ডার", "delivery", "ডেলিভারি", "কোথায় আমার", "where is my order"]):
        return "order_status"

    if any(x in text_lower for x in ["দাম", "price", "কত টাকা", "কত", "cost"]):
        return "price_check"

    if any(x in text_lower for x in ["available", "স্টকে", "স্টক আছে", "আছে", "ache", "ase", "in stock"]):
        # A catalog term plus an availability phrase is a product lookup.
        # A bare availability request is also a catalog browse with a stock filter.
        return "product_search" if terms or text_lower else "stock_check"

    if any(x in text_lower for x in ["দেখাও", "দেখান", "show", "find", "খুঁজে", "search", "what do you have", "কি কি", "কী কী", "what all"]):
        return "product_search"

    if terms:
        return "product_search"

    return "general_question"


COLORS = [
    "কালো", "সাদা", "লাল", "নীল", "সবুজ", "হলুদ",
    "black", "white", "red", "blue", "green", "yellow",
]


def extract_color(text: str) -> str | None:
    text_lower = text.lower()
    for color in COLORS:
        if color.lower() in text_lower:
            return color
    return None
