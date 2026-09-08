import re


def extract_max_price(
    text: str,
):

    patterns = [
        r"under\s+(\d+)",
        r"below\s+(\d+)",
        r"within\s+(\d+)",
        r"(\d+)\s*টাকার\s*মধ্যে",
        r"(\d+)\s*টাকার\s*নিচে",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text.lower(),
        )

        if match:

            return float(
                match.group(1)
            )

    return None
