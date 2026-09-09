"""Low-cost semantic intent detection for commerce follow-up requests.

The detector intentionally avoids maintaining an exhaustive phrase dictionary.
It combines normalized token/stem evidence and returns a tri-state decision:
True/False when local evidence is strong, None when an LLM fallback may help.
"""
from __future__ import annotations

import re
import unicodedata


# Only unambiguous destination/page markers live here. Generic commerce words
# such as "product", "shop" or "store" must never turn a product search into
# a link request by themselves.
_DIRECT_LINK_TERMS = {
    "link", "url", "website", "page", "permalink",
    "লিংক", "লিঙ্ক", "ওয়েবসাইট", "ওয়েবসাইট", "পেজ", "পারমালিংক",
}
_PURCHASE_STEMS = (
    "buy", "purchas", "order", "checkout", "kin", "ken", "nib", "neb",
    "kinb", "kinbo", "kinte", "kenbo", "kenar", "kinar",
    "অর্ডার", "কিন", "কেন", "কিনব", "কিনবো", "কিনতে", "কেনার", "নেব",
)
_DESTINATION_STEMS = (
    "where", "whereabouts", "kothay", "kotha", "kothai", "kothaay",
    "কোথায়", "কোথায়", "কোথা", "যেখান",
)
_ACTION_STEMS = (
    "give", "dao", "den", "diben", "show", "open", "send", "path", "pabo", "pab",
    "পাব", "পাওয়া", "দাও", "দেন", "দিবেন", "দেখাও", "দেখান", "খুল", "পাঠা",
)
_NEGATIVE_KNOWLEDGE_STEMS = (
    "office", "address", "location", "delivery", "shipping", "return", "refund",
    "policy", "support", "contact", "hours", "অফিস", "ঠিকানা", "লোকেশন",
    "ডেলিভারি", "শিপিং", "রিটার্ন", "রিফান্ড", "নীতি", "যোগাযোগ",
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
    """Return True/False for high-confidence cases, None only when ambiguous."""
    q = _normalize(message)
    if not q:
        return False
    tokens = _tokens(q)

    direct = any(token in _DIRECT_LINK_TERMS for token in tokens)
    purchase = _has_stem(tokens, _PURCHASE_STEMS)
    destination = _has_stem(tokens, _DESTINATION_STEMS)
    action = _has_stem(tokens, _ACTION_STEMS)
    negative = _has_stem(tokens, _NEGATIVE_KNOWLEDGE_STEMS)

    if direct:
        return True

    # "where can I buy/order/get it?" is a product-destination request even
    # when the user never says link, URL or website.
    if destination and purchase and not negative:
        return True

    # "where can I get it?" / "where do I find it?" can mean several things.
    # Return None so a caller with product context can use the existing LLM
    # stack as a rare fallback rather than maintaining endless phrases here.
    if destination and action and not negative:
        return None

    # Purchase + action without a destination is also ambiguous (e.g. a request
    # to explain how to buy). Let the context-aware fallback decide.
    if purchase and action and not negative:
        return None

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
