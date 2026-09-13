PRODUCT_TERMS = {
    "price",
    "dam",
    "stock",
    "available",
    "product",
    "ponno",
    "shoe",
    "juta",
}

WEBSITE_TERMS = {
    "return",
    "refund",
    "delivery",
    "shipping",
    "about",
    "policy",
    "contact",
    "return",
    "delivery",
    "policy",
}


def detect_tools(
    query: str,
):

    text = query.lower()

    product = any(
        term in text
        for term in PRODUCT_TERMS
    )

    website = any(
        term in text
        for term in WEBSITE_TERMS
    )

    return {
        "product": product,
        "website": website,
    }
