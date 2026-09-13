import re


def normalize_name(value: str) -> str:

    value = value.lower().strip()

    value = re.sub(
        r"([a-z])([A-Z])",
        r"\1_\2",
        value,
    )

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    return value.strip("_")
