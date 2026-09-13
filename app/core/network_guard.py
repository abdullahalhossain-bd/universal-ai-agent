"""
SSRF guard for merchant-supplied connection strings.

This module validates SQLAlchemy database connection URLs
(postgresql://..., mysql://...) and prevents connections to
private/internal/loopback/link-local addresses.

For local development only, set ALLOW_LOCAL_DATASOURCE_HOSTS=true.
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
    Recognize normal IP literals plus legacy integer/hex IPv4 forms.

    Some URL/network parsers accept 127.0.0.1 as 2130706433 or
    0x7f000001. Python's ipaddress module intentionally does not treat
    those strings as IPv4 literals, so normalize them explicitly before
    falling through to DNS resolution.
    """
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []

    try:
        candidates.append(ipaddress.ip_address(host))
    except ValueError:
        normalized = host.lower()
        try:
            if host.isdigit():
                value = int(host, 10)
                if 0 <= value <= 0xFFFFFFFF:
                    candidates.append(ipaddress.IPv4Address(value))
            elif normalized.startswith("0x"):
                value = int(normalized, 16)
                if 0 <= value <= 0xFFFFFFFF:
                    candidates.append(ipaddress.IPv4Address(value))
        except ValueError:
            pass

    return any(_is_dangerous_ip(ip) for ip in candidates)


def local_hosts_allowed() -> bool:
    return _local_hosts_allowed()


def _local_hosts_allowed() -> bool:
    return os.getenv("ALLOW_LOCAL_DATASOURCE_HOSTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def assert_safe_connection_host(connection_url: str) -> None:
    """Reject merchant-supplied database URLs targeting unsafe hosts."""
    if not connection_url:
        raise ValueError("connection_url is required")

    parsed = urlparse(connection_url)
    host = parsed.hostname
    if not host:
        raise ValueError("connection_url has no parseable host")

    host = host.rstrip(".").lower()
    allow_local = _local_hosts_allowed()

    if not allow_local and (
        host in _LOCAL_NAMES or host.endswith(".localhost")
    ):
        raise ValueError(f"Refusing to connect to local host: {host}")

    if not allow_local and _looks_dangerous_literal(host):
        raise ValueError(
            f"Refusing to connect to private/internal address: {host}"
        )

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host {host!r}: {exc}") from exc

    if allow_local:
        return

    for info in infos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise ValueError(
                f"Unparseable resolved address {ip_text!r} for host {host!r}"
            ) from exc

        if _is_dangerous_ip(ip):
            raise ValueError(
                f"Host {host!r} resolves to a private/internal address ({ip}); "
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
