import re


PRICE_PATTERN = re.compile(
    r"(?:৳|টাকা|taka|tk)\s*([0-9,]+)",
    re.IGNORECASE,
)


def extract_max_price(
    text: str,
) -> float | None:

    patterns = [
        r"([0-9,]+)\s*টাকার মধ্যে",
        r"([0-9,]+)\s*taka\s*এর মধ্যে",
        r"under\s*([0-9,]+)",
        r"below\s*([0-9,]+)",
        r"less than\s*([0-9,]+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:

            value = (
                match.group(1)
                .replace(",", "")
            )

            return float(value)

    return None


def wants_in_stock(
    text: str,
) -> bool | None:

    text = text.lower()

    positive = [
        "available",
        "in stock",
        "স্টকে",
        "স্টক আছে",
        "available আছে",
        "আছে",
    ]

    negative = [
        "out of stock",
        "স্টক নেই",
        "নেই",
    ]

    if any(x in text for x in positive):
        return True

    if any(x in text for x in negative):
        return False

    return None


def detect_intent(
    text: str,
) -> str:

    text_lower = text.lower()

    if any(
        x in text_lower
        for x in [
            "order",
            "অর্ডার",
            "delivery",
            "ডেলিভারি",
            "কোথায় আমার",
        ]
    ):
        return "order_status"

    if any(
        x in text_lower
        for x in [
            "দাম",
            "price",
            "কত টাকা",
            "কত",
        ]
    ):
        return "price_check"

    if any(
        x in text_lower
        for x in [
            "available",
            "স্টকে",
            "স্টক আছে",
        ]
    ):
        return "stock_check"

    if any(
        x in text_lower
        for x in [
            "দেখাও",
            "দেখান",
            "show",
            "find",
            "খুঁজে",
        ]
    ):
        return "product_search"

    return "general_question"


COLORS = [
    "কালো",
    "সাদা",
    "লাল",
    "নীল",
    "সবুজ",
    "হলুদ",
    "black",
    "white",
    "red",
    "blue",
    "green",
    "yellow",
]


def extract_color(
    text: str,
) -> str | None:

    text_lower = text.lower()

    for color in COLORS:

        if color.lower() in text_lower:
            return color

    return None
