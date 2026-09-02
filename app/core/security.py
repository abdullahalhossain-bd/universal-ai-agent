import hashlib
import secrets

from app.core.config import settings


def generate_api_key():
    """
    Generate a public/widget API key.

    The raw key is returned only at creation time.
    Only its SHA-256 hash should be stored in the database.
    """

    secret = secrets.token_urlsafe(32)

    full_key = (
        "pk_live_"
        + secret
    )

    key_hash = hashlib.sha256(
        full_key.encode("utf-8")
    ).hexdigest()

    prefix = full_key[:16]

    return (
        full_key,
        prefix,
        key_hash,
    )


def hash_api_key(
    key: str,
) -> str:

    return hashlib.sha256(
        key.encode("utf-8")
    ).hexdigest()


def get_trusted_proxies() -> list[str]:
    """
    Parse the comma-separated `trusted_proxies` setting into a
    list of exact IP strings. Empty list means "no proxy in
    front of this service", which is the safe default.
    """

    raw = (settings.trusted_proxies or "").strip()

    if not raw:
        return []

    return [
        part.strip()
        for part in raw.split(",")
        if part.strip()
    ]


def get_cors_allow_origins() -> list[str]:
    """
    Parse the comma-separated `cors_allow_origins` setting into
    a list for CORSMiddleware. Defaults to "*" (any origin) since
    the embeddable merchant widget runs on domains the platform
    does not control in advance; this is safe only because auth
    is a custom header rather than a cookie (see main.py).
    """

    raw = (settings.cors_allow_origins or "*").strip()

    if not raw:
        return ["*"]

    return [
        part.strip()
        for part in raw.split(",")
        if part.strip()
    ]


def resolve_client_ip(
    peer_host: str | None,
    forwarded_for: str | None,
) -> str:
    """
    Determine the real client IP for rate limiting.

    Anti-spoofing rules:

    - X-Forwarded-For is ONLY consulted when the direct TCP
      peer address appears in `trusted_proxies`. A client that
      sends a fake X-Forwarded-For while connecting directly
      therefore cannot rotate its rate-limit identity.
    - Among the forwarded chain, hops are scanned RIGHT to
      LEFT (the direction the proxy appends). The first entry
      that is not itself a trusted proxy is the client.
    - Anything unparseable falls back to the peer address.
    """

    peer = (peer_host or "unknown").strip() or "unknown"

    if not forwarded_for:
        return peer

    trusted = get_trusted_proxies()

    if peer not in trusted:
        # Peer is not a trusted proxy: the header is
        # client-controlled and must be ignored.
        return peer

    chain = [
        part.strip()
        for part in forwarded_for.split(",")
        if part.strip()
    ]

    if not chain:
        return peer

    # Walk right to left, skipping trusted proxies.
    for candidate in reversed(chain):
        if candidate not in trusted:
            return candidate

    # Every hop is a trusted proxy — the leftmost entry is
    # the best available identity.
    return chain[0]
