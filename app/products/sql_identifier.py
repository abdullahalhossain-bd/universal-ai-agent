import re


IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)


def validate_identifier(
    value: str,
) -> str:

    if not IDENTIFIER_PATTERN.match(
        value
    ):
        raise ValueError(
            f"Unsafe identifier: {value}"
        )

    return value
