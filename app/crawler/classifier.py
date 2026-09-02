def classify_url(url: str):

    url = url.lower()

    if "return" in url:
        return "return_policy"

    if "shipping" in url or "delivery" in url:
        return "shipping"

    if "faq" in url:
        return "faq"

    if "about" in url:
        return "about"

    if "contact" in url:
        return "contact"

    if "privacy" in url:
        return "privacy"

    if "terms" in url:
        return "terms"

    if "blog" in url:
        return "blog"

    return "unknown"
