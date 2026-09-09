"""Low-cost semantic intent detection for commerce follow-up requests.

The detector intentionally avoids maintaining an exhaustive phrase dictionary.
It combines normalized token/stem evidence and returns a tri-state decision:
True/False when local evidence is strong, None when an LLM fallback may help.
"""
from __future__ import annotations

import re
import unicodedata


_URL_TERMS = {
    "link", "url", "website", "web", "page", "shop", "store", "product",
    "লিংক", "লিঙ্ক", "ওয়েবসাইট", "ওয়েবসাইট", "পেজ", "পাতা", "শপ", "দোকান",
}
_PURCHASE_STEMS = (
    "buy", "purchas", "order", "checkout", "shop", "kin", "ken", "nib", "neb",
    "kinb", "kinbo", "kinte", "kenbo", "kenar", "kinar", "অর্ডার", "কিন", "কেন",
    "কিনব", "কিনবো", "কিনতে", "কেনার", "কোথা থেকে অর্ডার", "নেব",
)
_DESTINATION_TERMS = {
    "where", "whereabouts", "kothay", "kotha", "kothai", "kothay", "kothaay",
    "কোথায়", "কোথায়", "কোথা", "যেখান", "কোথা থেকে",
}
_ACTION_STEMS = (
    "give", "dao", "den", "diben", "show", "open", "send", "path", "পাব", "পাওয়া",
    "দাও", "দেন", "দিবেন", "দেখাও", "দেখান", "খুল", "পাঠা",
)
_NEGATIVE_KNOWLEDGE_STEMS = (
    "office", "address", "location", "delivery", "shipping", "return", "refund",
    "policy", "support", "contact", "অফিস", "ঠিকানা", "ডেলিভারি", "শিপিং", "রিটার্ন", "রিফান্ড",
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    text = re.sub(r"[!?.,:;()\[\]{}\"'`]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", text) if t]


def _has_stem(tokens: list[str], stems: tuple[str, ...]) -> bool:
    return any(any(token.startswith(stem) for stem in stems) for token in tokens)


def classify_product_link_request(message: str) -> bool | None:
    """Return True/False for high-confidence cases, None for ambiguity."""
    q = _normalize(message)
    if not q:
        return False
    tokens = _tokens(q)

    direct = sum(1 for token in tokens if token in _URL_TERMS)
    purchase = _has_stem(tokens, _PURCHASE_STEMS)
    destination = _has_stem(tokens, _DESTINATION_TERMS)
    action = _has_stem(tokens, _ACTION_STEMS)
    negative = _has_stem(tokens, _NEGATIVE_KNOWLEDGE_STEMS)

    # Explicit page/link language is deterministic even without context.
    if direct >= 1:
        return True

    # Natural shopping language: "where can I buy it?", "where do I get it?".
    # This is semantic feature composition, not a phrase allow-list.
    if destination and purchase and not negative:
        return True

    # "where can I get/find it" is ambiguous by itself; with a product context
    # the caller can safely ask the LLM fallback to distinguish product purchase
    # intent from a generic knowledge/location question.
    if destination and action and not negative:
        return None

    # Purchase/order language without a destination is usually a product action,
    # but only treat it as a link request when it also points to a product/page.
    if purchase and action and not negative:
        return None

    # A bare destination question should not hijack knowledge queries.
    if destination:
        return False

    return False


def parse_llm_link_intent(text: str) -> bool | None:
    """Parse a strict classifier answer without trusting free-form prose."""
    normalized = _normalize(text)
    if not normalized:
        return None
    if re.search(r"\b(?:true|yes|product[_ -]?link[_ -]?request)\b", normalized):
        return True
    if re.search(r"\b(?:false|no|not[_ -]?a[_ -]?product[_ -]?link)\b", normalized):
        return False
    return None
