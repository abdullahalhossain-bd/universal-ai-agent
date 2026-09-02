"""
SSRF guard for merchant-supplied connection strings.

This module validates SQLAlchemy database connection URLs
(postgresql://..., mysql://...) and prevents connections to
private/internal/loopback/link-local addresses.

For local development only, set:

    ALLOW_LOCAL_DATASOURCE_HOSTS=true

This allows localhost/private addresses so a locally running
merchant database can be used during development.

In production, do NOT enable ALLOW_LOCAL_DATASOURCE_HOSTS.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


_LOCAL_NAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
    }
)


def _is_dangerous_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Return True when an IP belongs to a private/internal or otherwise
    unsafe address range.
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _looks_dangerous_literal(host: str) -> bool:
    """
    Fast-path check for hosts that Python's ipaddress module can parse
    directly as IPv4/IPv6 literals.

    Numeric hostname encodings that ipaddress does not understand are
    intentionally handled later by socket.getaddrinfo().
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return _is_dangerous_ip(ip)


def _local_hosts_allowed() -> bool:
    """
    Development-only escape hatch.

    Truthy values:
        1
        true
        yes
        on

    Production should leave this unset/false.
    """
    return os.getenv(
        "ALLOW_LOCAL_DATASOURCE_HOSTS",
        "",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def assert_safe_connection_host(connection_url: str) -> None:
    """
    Validate a merchant-supplied database connection URL.

    By default, the function rejects:

    - localhost
    - .localhost domains
    - loopback addresses
    - private addresses
    - link-local addresses
    - reserved addresses
    - multicast addresses
    - unspecified addresses
    - public-looking hostnames resolving to private/internal IPs

    This protects the application from SSRF-style attacks through
    merchant-supplied database connection URLs.

    For local development only:

        ALLOW_LOCAL_DATASOURCE_HOSTS=true

    skips the private/local address rejection.

    DNS resolution is still performed before the local-development
    shortcut so malformed/unresolvable hosts are still rejected.
    """

    if not connection_url:
        raise ValueError("connection_url is required")

    parsed = urlparse(connection_url)
    host = parsed.hostname

    if not host:
        raise ValueError(
            "connection_url has no parseable host"
        )

    host = host.rstrip(".").lower()

    allow_local = _local_hosts_allowed()

    # ---------------------------------------------------------------
    # Explicit localhost hostname protection
    # ---------------------------------------------------------------

    if (
        not allow_local
        and (
            host in _LOCAL_NAMES
            or host.endswith(".localhost")
        )
    ):
        raise ValueError(
            f"Refusing to connect to local host: {host}"
        )

    # ---------------------------------------------------------------
    # Literal IP protection
    # ---------------------------------------------------------------

    if not allow_local and _looks_dangerous_literal(host):
        raise ValueError(
            f"Refusing to connect to private/internal address: {host}"
        )

    # ---------------------------------------------------------------
    # DNS resolution
    #
    # This is important because a hostname such as:
    #
    #     database.example.com
    #
    # could resolve to:
    #
    #     127.0.0.1
    #     10.x.x.x
    #     172.16.x.x
    #     192.168.x.x
    #     169.254.x.x
    #
    # and bypass a simple hostname string check.
    # ---------------------------------------------------------------

    try:
        infos = socket.getaddrinfo(
            host,
            None,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(
            f"Cannot resolve host {host!r}: {exc}"
        ) from exc

    # ---------------------------------------------------------------
    # Local-development mode
    #
    # We already successfully parsed and resolved the hostname.
    # In development mode we intentionally allow local/private
    # addresses.
    # ---------------------------------------------------------------

    if allow_local:
        return

    # ---------------------------------------------------------------
    # Production/default protection
    # ---------------------------------------------------------------

    for info in infos:
        ip_text = info[4][0]

        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise ValueError(
                f"Unparseable resolved address "
                f"{ip_text!r} for host {host!r}"
            ) from exc

        if _is_dangerous_ip(ip):
            raise ValueError(
                f"Host {host!r} resolves to a "
                f"private/internal address ({ip}); "
                "refusing to connect"
            )


def assert_safe_http_url(url: str) -> None:
    """Reject unsafe merchant REST URLs before an outbound request."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("REST URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("REST URL must not contain credentials")
    assert_safe_connection_host(url)