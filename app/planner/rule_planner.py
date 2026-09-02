import re

from app.planner.models import (
    Intent,
    PlannedAction,
    ProductFilters,
)


PRODUCT_WORDS = {
    "product",
    "products",
    "shoe",
    "shoes",
    "shirt",
    "shirts",
    "phone",
    "laptop",
    "watch",
    "bag",
    "dress",
    "জুতা",
    "জুতো",
    "জামা",
    "শার্ট",
    "মোবাইল",
    "ল্যাপটপ",
    "ঘড়ি",
    "ব্যাগ",
    "ড্রেস",
}


KNOWLEDGE_WORDS = {
    "policy",
    "return",
    "refund",
    "shipping",
    "delivery",
    "about",
    "contact",
    "faq",
    "how",
    "when",
    "নীতি",
    "রিটার্ন",
    "রিফান্ড",
    "ডেলিভারি",
    "শিপিং",
    "সম্পর্কে",
    "যোগাযোগ",
    "কীভাবে",
    "কখন",
}


STOP_WORDS = {
    "show",
    "find",
    "me",
    "please",
    "available",
    "in",
    "stock",
    "under",
    "below",
    "within",
    "price",
    "টাকার",
    "টাকা",
    "মধ্যে",
    "জন্য",
    "দেখাও",
    "দেখান",
    "চাই",
    "আছে",
    "স্টকে",
    "স্টক",
    "এর",
    "ও",
    "আর",
    "এবং",
    "and",
    "কী",
    "কি",
    "এমন",
    "যেমন",
    "মতো",
    "মত",
    "কম",
    "কমে",
    "নিচে",
    "উপরে",
    "বেশি",
}


def _normalize_digits(text: str) -> str:
    translation = str.maketrans(
        "০১২৩৪৫৬৭৮৯"
        "٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789",
    )

    return text.translate(translation)


def _extract_max_price(
    text: str,
) -> float | None:

    text = _normalize_digits(text)

    patterns = [
        r"([0-9][0-9,]*)\s*টাকার\s*মধ্যে",
        r"([0-9][0-9,]*)\s*টাকা\s*র মধ্যে",
        r"([0-9][0-9,]*)\s*taka\s*এর মধ্যে",
        r"([0-9][0-9,]*)\s*টাকার\s*কমে?",
        r"([0-9][0-9,]*)\s*টাকার\s*নিচে",
        r"under\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"below\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"within\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"(?:৳|tk|taka)\s*([0-9][0-9,]*)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        value = (
            match.group(1)
            .replace(",", "")
        )

        try:
            return float(value)
        except ValueError:
            continue

    return None


def _extract_min_price(
    text: str,
) -> float | None:

    text = _normalize_digits(text)

    patterns = [
        r"(?:above|over|more than)\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*টাকার\s*উপরে",
        r"([0-9][0-9,]*)\s*টাকার\s*বেশি",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        value = (
            match.group(1)
            .replace(",", "")
        )

        try:
            return float(value)
        except ValueError:
            continue

    return None


def _extract_in_stock(
    text: str,
) -> bool:

    stock_words = {
        "available",
        "in stock",
        "stock আছে",
        "স্টকে আছে",
        "স্টক আছে",
        "available আছে",
    }

    lowered = text.lower()

    return any(
        word in lowered
        for word in stock_words
    )


def _clean_search_terms(
    text: str,
    exclude_words: set[str] | None = None,
) -> str:

    cleaned = text

    # Remove price phrases.
    cleaned = re.sub(
        r"[0-9][0-9,]*\s*টাকার\s*মধ্যে",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"[0-9][0-9,]*\s*taka\s*এর মধ্যে",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"(?:under|below|within)\s*(?:৳\s*)?[0-9][0-9,]*",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"(?:৳|tk|taka)\s*[0-9][0-9,]*",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Tokenize.
    tokens = cleaned.split()

    useful = []

    for token in tokens:

        token = token.strip(
            ".,!?;:()[]{}\"'"
        )

        if not token:
            continue

        if token.lower() in STOP_WORDS:
            continue

        if (
            exclude_words
            and token.lower() in exclude_words
        ):
            continue

        if token.isdigit():
            continue

        useful.append(token)

    return " ".join(useful)


def plan(query: str):

    text = query.lower()

    product_score = sum(
        word in text
        for word in PRODUCT_WORDS
    )

    knowledge_score = sum(
        word in text
        for word in KNOWLEDGE_WORDS
    )

    max_price = _extract_max_price(
        query
    )

    min_price = _extract_min_price(
        query
    )

    in_stock = _extract_in_stock(
        query
    )

    search_terms = _clean_search_terms(
        query
    )

    # ---------------------------------
    # Mixed query
    # ---------------------------------

    if (
        product_score > 0
        and knowledge_score > 0
    ):

        product_search_terms = (
            _clean_search_terms(
                query,
                exclude_words=KNOWLEDGE_WORDS,
            )
        )

        knowledge_search_terms = (
            _clean_search_terms(
                query,
                exclude_words=PRODUCT_WORDS,
            )
        )

        return PlannedAction(
            intent=Intent.MIXED,

            product_filters=ProductFilters(
                product_name=product_search_terms
                or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),

            knowledge_query=(
                knowledge_search_terms
                or query
            ),

            confidence=0.90,
        )

    # ---------------------------------
    # Product query
    # ---------------------------------

    if product_score > 0:

        return PlannedAction(
            intent=Intent.PRODUCT_SEARCH,

            product_filters=ProductFilters(
                product_name=search_terms
                or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),

            confidence=0.90,
        )

    # ---------------------------------
    # Price-only query can still be
    # treated as product intent when
    # a product term exists elsewhere.
    # ---------------------------------

    if (
        max_price is not None
        and search_terms
    ):

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

    # ---------------------------------
    # Knowledge query
    # ---------------------------------

    if knowledge_score > 0:

        return PlannedAction(
            intent=Intent.KNOWLEDGE_SEARCH,
            knowledge_query=query,
            confidence=0.75,
        )

    # ---------------------------------
    # Unknown
    # ---------------------------------

    return PlannedAction(
        intent=Intent.UNKNOWN,
        confidence=0.20,
    )