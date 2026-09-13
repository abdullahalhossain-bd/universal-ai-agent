from __future__ import annotations

from urllib.parse import urlparse


def classify_page(url: str, title: str | None = None, content: str | None = None, structured_data: list[dict] | None = None) -> str:
    """Classify a page from multiple runtime signals.

    URL hints are only a weak fallback. Structured data and page content take
    precedence so unrelated merchant URL conventions do not require code changes.
    """
    text = " ".join([str(title or ""), str(content or "")]).casefold()
    path = urlparse(url).path.casefold()
    structured_data = structured_data or []
    types = {
        str(item.get("@type", "")).casefold()
        for item in structured_data
        if isinstance(item, dict)
    }
    if "product" in types:
        return "product"
    if any(t in types for t in ("faqpage", "question")):
        return "faq"
    if "article" in types or "blogposting" in types:
        return "blog"

    signals = (
        ("return_policy", ("return policy", "refund policy", "returns")),
        ("shipping", ("shipping", "delivery information", "delivery policy")),
        ("faq", ("frequently asked questions", "faq", "questions and answers")),
        ("contact", ("contact us", "contact information")),
        ("about", ("about us", "our story", "who we are")),
        ("privacy", ("privacy policy", "privacy notice")),
        ("terms", ("terms and conditions", "terms of service")),
    )
    for page_type, needles in signals:
        if any(n in text for n in needles):
            return page_type

    path_hints = (
        ("return_policy", ("return", "refund")),
        ("shipping", ("shipping", "delivery")),
        ("faq", ("faq",)),
        ("contact", ("contact",)),
        ("about", ("about",)),
        ("privacy", ("privacy",)),
        ("terms", ("terms",)),
        ("blog", ("blog", "article")),
    )
    for page_type, needles in path_hints:
        if any(n in path for n in needles):
            return page_type
    return "general"


def classify_url(url: str):
    """Backward-compatible wrapper; URL hints are intentionally weak."""
    return classify_page(url)
