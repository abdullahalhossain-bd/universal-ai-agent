from urllib.parse import (
    urlparse,
)


BLOCKED_PATHS = {
    "/login",
    "/logout",
    "/cart",
    "/checkout",
    "/admin",
}


def is_allowed_url(
    url: str,
    base_domain: str,
) -> bool:

    parsed = urlparse(url)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return False

    if parsed.netloc != base_domain:
        return False

    path = parsed.path.rstrip("/")

    if path in BLOCKED_PATHS:
        return False

    return True
