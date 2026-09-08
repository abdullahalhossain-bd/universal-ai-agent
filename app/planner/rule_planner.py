from __future__ import annotations

import re
from enum import Enum

from app.planner.models import PlannedAction, ProductFilters


class Intent(str, Enum):
    PRODUCT_SEARCH = "product_search"
    KNOWLEDGE_SEARCH = "knowledge_search"
    MIXED = "mixed"
    UNKNOWN = "unknown"


PRODUCT_WORDS = {
    "product",
    "products",
    "laptop",
    "laptops",
    "notebook",
    "notebooks",
    "computer",
    "computers",
    "pc",
    "desktop",
    "phone",
    "phones",
    "mobile",
    "mobiles",
    "smartphone",
    "tablet",
    "tablets",
    "ipad",
    "iphone",
    "android",
    "earphone",
    "earphones",
    "earbud",
    "earbuds",
    "headphone",
    "headphones",
    "mouse",
    "keyboard",
    "monitor",
    "printer",
    "camera",
    "watch",
    "shoes",
    "shoe",
    "sandal",
    "sandals",
    "bag",
    "bags",
    "mobile",
    "মোবাইল",
    "ল্যাপটপ",
    "কম্পিউটার",
    "ফোন",
    "ফোনের",
    "ট্যাব",
    "ইয়ারফোন",
    "হেডফোন",
    "মাউস",
    "কিবোর্ড",
    "কীবোর্ড",
    "মনিটর",
    "প্রিন্টার",
    "ক্যামেরা",
    "জুতা",
    "জুতো",
    "স্যান্ডেল",
    "ব্যাগ",
}

KNOWLEDGE_WORDS = {
    "how",
    "what",
    "why",
    "when",
    "where",
    "which",
    "who",
    "can",
    "does",
    "do",
    "is",
    "are",
    "explain",
    "meaning",
    "policy",
    "shipping",
    "delivery",
    "return",
    "refund",
    "warranty",
    "support",
    "কিভাবে",
    "কীভাবে",
    "কি",
    "কী",
    "কেন",
    "কখন",
    "কোথায়",
    "কোথায়",
    "কোন",
    "কোনটি",
    "নীতি",
    "শিপিং",
    "ডেলিভারি",
    "রিটার্ন",
    "রিফান্ড",
    "ওয়ারেন্টি",
    "ওয়ারেন্টি",
}

# Conversational words that must not become literal product search terms.
# In particular, without the Banglish forms, "laptop ase" becomes an
# AND query for both "laptop" and "ase" and can incorrectly return zero rows.
STOP_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "am",
    "do",
    "does",
    "did",
    "you",
    "have",
    "has",
    "please",
    "me",
    "my",
    "your",
    "show",
    "find",
    "give",
    "want",
    "need",
    "for",
    "to",
    "in",
    "on",
    "with",
    "of",
    "and",
    "or",
    "available",
    "stock",
    "under",
    "below",
    "within",
    "price",
    "cost",
    "taka",
    "tk",
    "ase",
    "ache",
    "ache?",
    "asche",
    "asha",
    "chai",
    "dekhao",
    "dekhan",
    "stoke",
    "আছে",
    "আছেন",
    "চাই",
    "দেখাও",
    "দেখান",
    "দাও",
    "দেন",
    "আমার",
    "আপনার",
    "আছে?",
    "স্টকে",
    "স্টক",
    "দাম",
    "মূল্য",
    "টাকা",
    "টাকার",
    "মধ্যে",
    "এর",
}


def _extract_max_price(text: str) -> float | None:
    patterns = [
        r"(?:under|below|within)\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*taka\s*এর মধ্যে",
        r"([0-9][0-9,]*)\s*টাকার\s*মধ্যে",
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
    patterns = [
        r"(?:over|above|more than|greater than)\s*(?:৳\s*)?([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s*taka\s*এর বেশি",
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
    stock_phrases = {
        "available",
        "in stock",
        "stock আছে",
        "স্টকে আছে",
        "স্টক আছে",
        "available আছে",
        # Banglish conversational availability.
        "stock ase",
        "stock ache",
        "available ase",
        "available ache",
        "ase",
        "ache",
        "আছে",
    }
    return any(phrase in lowered for phrase in stock_phrases)


def _clean_search_terms(
    text: str,
    exclude_words: set[str] | None = None,
) -> str:
    cleaned = text

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

    tokens = cleaned.split()
    useful = []
    for token in tokens:
        token = token.strip(".,!?;:()[]{}\"'")
        if not token:
            continue
        if token.lower() in STOP_WORDS:
            continue
        if exclude_words and token.lower() in exclude_words:
            continue
        if token.isdigit():
            continue
        useful.append(token)
    return " ".join(useful)


def _looks_like_model_number(token: str) -> bool:
    if not token:
        return False
    has_letter = any(ch.isalpha() for ch in token)
    has_digit = any(ch.isdigit() for ch in token)
    return has_letter and has_digit


def plan(query: str, store_terms: set[str] | None = None):
    """Plan product/knowledge intent using both generic and merchant vocabulary."""
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
        product_search_terms = _clean_search_terms(
            query,
            exclude_words=KNOWLEDGE_WORDS,
        )
        knowledge_search_terms = _clean_search_terms(
            query,
            exclude_words=PRODUCT_WORDS,
        )
        return PlannedAction(
            intent=Intent.MIXED,
            product_filters=ProductFilters(
                product_name=product_search_terms or None,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            ),
            knowledge_query=knowledge_search_terms or query,
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

    return PlannedAction(
        intent=Intent.UNKNOWN,
        confidence=0.0,
    )
