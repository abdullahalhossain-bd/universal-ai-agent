"""Deterministic conversation intelligence for ecommerce chat follow-ups.

This module deliberately does not call an LLM. It resolves common conversational
references against the products returned in the immediately preceding turn so
simple commerce actions stay fast, cheap, and predictable.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FollowUpResolution:
    """Resolved meaning of a follow-up message."""

    action: str | None = None
    product_index: int | None = None
    product_ids: tuple[str, ...] = ()
    is_follow_up: bool = False
    confidence: float = 0.0


_LINK_TERMS = ("link", "url", "website", "product page", "লিংক", "লিঙ্ক", "ওয়েবসাইট", "ওয়েবসাইট")
_IMAGE_TERMS = ("image", "photo", "picture", "pic", "ছবি", "ইমেজ", "ফটো")
_PRICE_TERMS = ("price", "cost", "dam", "দাম", "মূল্য", "কত টাকা", "koto taka")
_STOCK_TERMS = ("stock", "available", "availability", "ase", "ache", "আছে", "আছে়", "স্টকে", "উপলব্ধ")
_COMPARE_TERMS = ("compare", "comparison", "difference", "egula compare", "তুলনা", "পার্থক্য", "compare kore")

_GENERIC_ACTION_WORDS = {
    "the", "this", "that", "it", "one", "product", "please", "show", "give", "dao", "den",
    "দাও", "দেন", "দেখাও", "দেখান", "ওই", "ওটা", "এটা", "টার", "টা", "টি", "এর", "র",
    "tar", "ta", "ti", "er", "r", "koro", "kor", "egula", "egulo", "these", "those",
}

_ORDINALS = {
    "first": 1, "1st": 1, "one": 1, "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3, "fourth": 4, "4th": 4, "four": 4,
    "fifth": 5, "5th": 5, "five": 5, "sixth": 6, "6th": 6, "six": 6,
    "seventh": 7, "7th": 7, "seven": 7, "eighth": 8, "8th": 8, "eight": 8,
    "ninth": 9, "9th": 9, "nine": 9, "tenth": 10, "10th": 10, "ten": 10,
    "প্রথম": 1, "দ্বিতীয়": 2, "দ্বিতীয়": 2, "তৃতীয়": 3, "তৃতীয়": 3,
    "চতুর্থ": 4, "পঞ্চম": 5, "ষষ্ঠ": 6, "সপ্তম": 7, "অষ্টম": 8, "নবম": 9, "দশম": 10,
}


def _normalize(text: str) -> str:
    text = str(text or "").casefold().strip()
    text = text.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))
    text = re.sub(r"[!?.,;:()\[\]{}\"'“”‘’]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_product_index(message: str) -> int | None:
    """Extract a human product position such as '2nd', 'second', or 'তৃতীয়টা'."""
    q = _normalize(message)
    for token, index in sorted(_ORDINALS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", q):
            return index
    patterns = (
        r"\b(\d{1,2})\s*(?:st|nd|rd|th)\b",
        r"\b(\d{1,2})\s*(?:number|no\.?|num)\b",
        r"(?:^|\s)(\d{1,2})\s*(?:নম্বর|নং|নম্বরের)(?:টা|টি|টার|টির)?(?:\s|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 100:
                return value
    return None


def _has_any(q: str, terms: Sequence[str]) -> bool:
    return any(term in q for term in terms)


def _looks_like_context_reference(q: str) -> bool:
    tokens = q.split()
    if not tokens:
        return False
    if any(token in {"eta", "etar", "otar", "ota", "oi", "that", "this", "it", "ওই", "ওটা", "এটা", "সেটা", "সেটার", "তার", "ওইটার", "ওটার"} for token in tokens):
        return True
    if extract_product_index(q) is not None or _has_any(q, _COMPARE_TERMS):
        return True
    useful = [token for token in tokens if token not in _GENERIC_ACTION_WORDS]
    return not useful


def _product_id(product: Mapping[str, Any]) -> str | None:
    for key in ("id", "product_id", "uuid"):
        value = product.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def resolve_follow_up(message: str, products: Sequence[Mapping[str, Any]] | None) -> FollowUpResolution:
    """Resolve a follow-up against a previous product result set.

    Supported deterministic actions: product link, image, price, stock, comparison,
    and selecting a numbered/ordinal product. Unknown requests intentionally return
    no action so the normal planner/LLM path can handle them.
    """
    q = _normalize(message)
    previous = list(products or [])
    if not q or not previous or not _looks_like_context_reference(q):
        return FollowUpResolution()

    ids = tuple(pid for pid in (_product_id(product) for product in previous) if pid)
    index = extract_product_index(q)
    selected = ()
    if index is not None and 1 <= index <= len(previous):
        pid = _product_id(previous[index - 1])
        selected = (pid,) if pid else ()

    action: str | None = None
    if _has_any(q, _LINK_TERMS):
        action = "product_link"
    elif _has_any(q, _IMAGE_TERMS):
        action = "product_image"
    elif _has_any(q, _COMPARE_TERMS):
        action = "compare_products"
    elif _has_any(q, _PRICE_TERMS):
        action = "product_price"
    elif _has_any(q, _STOCK_TERMS):
        action = "product_stock"
    elif index is not None:
        action = "select_product"

    if action is None and len(previous) == 1:
        selected = ids
        action = "select_product"
    if action is None:
        return FollowUpResolution()

    confidence = 0.98 if index is not None else (0.94 if len(previous) == 1 else 0.88)
    resolved_ids = (selected or ids) if action == "compare_products" else selected
    return FollowUpResolution(action=action, product_index=index, product_ids=resolved_ids, is_follow_up=True, confidence=confidence)
