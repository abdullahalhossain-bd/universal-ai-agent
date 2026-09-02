def plan_query(text: str):

    text = text.lower()

    product_words = [
        "product",
        "price",
        "stock",
        "shoe",
        "phone",
        "laptop",
        "ponno",
        "dam",
        "stock",
        "juta",
        "phone",
    ]

    website_words = [
        "return",
        "refund",
        "delivery",
        "shipping",
        "policy",
        "about",
        "return",
        "delivery",
        "policy",
    ]

    use_product = any(
        word in text
        for word in product_words
    )

    use_knowledge = any(
        word in text
        for word in website_words
    )

    return {
        "use_product_search":
            use_product,

        "use_knowledge_search":
            use_knowledge,
    }
