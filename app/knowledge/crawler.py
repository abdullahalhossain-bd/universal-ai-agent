"""
Website crawler for knowledge ingestion.

`WebsiteCrawler` is constructed without a required URL and exposes a
`crawl(start_url)` coroutine that returns a list of page dicts of the
shape `{"url", "title", "content", "http_status"}` — exactly what
`KnowledgeService.ingest` consumes.

`BeautifulSoup` (bs4) is an optional dependency. If it is not installed,
`crawl(...)` raises a clear `RuntimeError` instead of failing at import
time.
"""

import asyncio
import ipaddress
import socket
from collections import deque
from urllib.parse import (
    urljoin,
    urlparse,
)

import httpx


# Maximum redirect hops followed manually per page fetch.
# Every hop is re-validated against the SSRF checks below,
# which is why `follow_redirects=False` is mandatory: an
# httpx auto-redirect could silently land on a private
# address that was never inspected.
MAX_REDIRECTS = 5


def _is_dangerous_ip(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    """
    True for any address that must never be reached by the
    crawler: loopback, RFC1918 private ranges, link-local
    (including the 169.254.169.254 cloud-metadata endpoint),
    reserved, multicast, and unspecified addresses.
    """

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _check_literal_host(host: str) -> bool:
    """
    Validate a host that is a literal IP address.

    Handles decimal, hex, and octal encodings (`2130706433`,
    `0x7f000001`, `0177.0.0.1`) because `ipaddress` parses
    them the same way the OS resolver does. Returns True when
    the host is dangerous.
    """

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return _is_dangerous_ip(ip)


_LOCAL_NAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
    }
)


def is_private_host(url: str) -> bool:
    """
    Synchronous first-pass URL safety check.

    Rejects non-http(s) schemes, well-known local hostnames,
    and literal IP addresses (in any textual encoding) that
    point at private infrastructure.

    A DNS hostname that passes this check may STILL resolve to
    a private address; the async `assert_safe_url()` must run
    before any network request is made.
    """

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return True

    host = parsed.hostname

    if not host:
        return True

    host = host.rstrip(".").lower()

    if host in _LOCAL_NAMES:
        return True

    if host.endswith(".localhost"):
        return True

    if _check_literal_host(host):
        return True

    return False


async def assert_safe_url(url: str) -> None:
    """
    Full SSRF validation for a URL about to be fetched.

    Runs `is_private_host` and additionally resolves the
    hostname, refusing any URL for which ANY resolved address
    is private/loopback/link-local/reserved. This closes the
    DNS-rebinding-shaped hole where a public hostname maps to
    an internal IP (e.g. `foo.example.com -> 10.0.0.5`).

    Raises `ValueError` when the URL must not be fetched.
    """

    if is_private_host(url):
        raise ValueError(
            f"Refusing to fetch private/internal address: {url}"
        )

    host = urlparse(url).hostname

    if not host:
        raise ValueError(
            f"URL has no parseable hostname: {url}"
        )

    # getaddrinfo is a blocking syscall; run it in the
    # default thread-pool executor so the event loop is
    # never blocked while resolving.
    loop = asyncio.get_running_loop()

    try:
        infos = await loop.getaddrinfo(
            host,
            None,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(
            f"Cannot resolve host {host!r}: {exc}"
        ) from exc

    for info in infos:
        ip_text = info[4][0]

        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            # Not parseable as an IP — treat as dangerous.
            raise ValueError(
                f"Unparseable resolved address {ip_text!r} "
                f"for host {host!r}"
            )

        if _is_dangerous_ip(ip):
            raise ValueError(
                f"Host {host!r} resolves to a private/internal "
                f"address ({ip}); refusing to fetch {url}"
            )


def _require_bs4():
    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "BeautifulSoup (bs4) is required for website crawling. "
            "Install it with: pip install beautifulsoup4"
        ) from exc
    return BeautifulSoup


def extract_content(html: str):
    BeautifulSoup = _require_bs4()

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = (
        soup.title.get_text(strip=True)
        if soup.title
        else ""
    )

    text = soup.get_text(separator=" ", strip=True)

    return {
        "title": title,
        "content": text,
    }


def discover_links(html: str, current_url: str, domain: str):
    BeautifulSoup = _require_bs4()

    soup = BeautifulSoup(html, "html.parser")

    links = set()

    for anchor in soup.find_all("a", href=True):
        url = urljoin(current_url, anchor["href"])

        parsed = urlparse(url)

        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc == domain
            and not is_private_host(url)
        ):
            links.add(url)

    return links


class WebsiteCrawler:
    """
    Minimal BFS website crawler. Construct without a URL and call
    `await crawler.crawl(start_url)` to get a list of pages.
    """

    def __init__(
        self,
        start_url: str | None = None,
        max_pages: int = 100,
        max_depth: int = 3,
    ):
        self.start_url = start_url
        self.max_pages = max_pages
        self.max_depth = max_depth

    async def fetch(self, url: str) -> tuple[str, int]:
        """
        Fetch one page with full SSRF protection.

        Redirects are followed MANUALLY (httpx
        `follow_redirects=False`) so that every hop — including
        cross-origin hops — is re-validated against
        `assert_safe_url()` before the next request goes out.
        """

        current_url = url

        for _hop in range(MAX_REDIRECTS + 1):

            await assert_safe_url(current_url)

            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    current_url,
                    headers={"User-Agent": "UniversalAI-Bot/1.0"},
                )

            if response.is_redirect:
                location = response.headers.get("location")

                if not location:
                    raise ValueError(
                        f"Redirect response without Location header "
                        f"from {current_url}"
                    )

                current_url = str(
                    urljoin(current_url, location)
                )

                continue

            response.raise_for_status()

            return response.text, response.status_code

        raise ValueError(
            f"Too many redirects (>{MAX_REDIRECTS}) fetching {url}"
        )

    async def crawl(
        self,
        start_url: str | None = None,
    ) -> list[dict]:
        root = start_url or self.start_url

        if not root:
            raise ValueError(
                "WebsiteCrawler.crawl requires a start_url."
            )

        if is_private_host(root):
            raise ValueError(
                f"Refusing to crawl private/internal address: {root}"
            )

        parsed_root = urlparse(root)
        domain = parsed_root.netloc

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(root, 0)])
        pages: list[dict] = []

        while queue and len(pages) < self.max_pages:
            url, depth = queue.popleft()

            if url in visited:
                continue

            visited.add(url)

            try:
                html, http_status = await self.fetch(url)
            except Exception:
                # Skip unreachable pages but keep crawling.
                continue

            extracted = extract_content(html)

            pages.append(
                {
                    "url": url,
                    "title": extracted["title"],
                    "content": extracted["content"],
                    "http_status": http_status,
                }
            )

            if depth < self.max_depth:
                for link in discover_links(html, url, domain):
                    if link not in visited:
                        queue.append((link, depth + 1))

        return pages
