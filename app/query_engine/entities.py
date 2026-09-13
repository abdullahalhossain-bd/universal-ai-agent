import re


def extract_price(text: str):

    match = re.search(
        r"(\d{2,7})\s*(taka|tk|৳|টাকা)?",
        text,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def extract_color(text: str):

    colors = [
        "black",
        "white",
        "red",
        "blue",
        "green",
        "yellow",
        "কালো",
        "সাদা",
        "লাল",
        "নীল",
    ]

    text_lower = text.lower()

    for color in colors:

        if color in text_lower:
            return color

    return None


def extract_entities(text: str):

    return {
        "max_price": extract_price(text),
        "color": extract_color(text),
    }
