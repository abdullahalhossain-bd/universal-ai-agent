"""Tenant-safe, bounded website crawler used by dynamic ingestion."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import httpx

from app.core.config import settings
from app.core.network_guard import local_hosts_allowed as _local_hosts_allowed
from app.crawler.parser import parse_page
from app.crawler.sitemap import parse_sitemap

MAX_REDIRECTS = 5


def _is_dangerous_ip(ip):
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _check_literal_host(host: str) -> bool:
    try:
        return _is_dangerous_ip(ipaddress.ip_address(host))
    except ValueError:
        return False


_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", "metadata.google.internal"})


def is_private_host(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or _local_hosts_allowed():
        return False
    host = (parsed.hostname or "").rstrip(".").lower()
    return not host or host in _LOCAL_NAMES or host.endswith(".localhost") or _check_literal_host(host)


async def assert_safe_url(url: str) -> None:
    if is_private_host(url):
        raise ValueError(f"Refusing to fetch private/internal address: {url}")
    host = urlparse(url).hostname
    if not host:
        raise ValueError(f"URL has no parseable hostname: {url}")
    if _local_hosts_allowed():
        return
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, None, type=socket.SOCK_STREAM))
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError as exc:
            raise ValueError(f"Unparseable resolved address for host {host!r}") from exc
        if _is_dangerous_ip(ip):
            raise ValueError(f"Host {host!r} resolves to a private/internal address; refusing to fetch {url}")


def _require_bs4():
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("BeautifulSoup (bs4) is required for website crawling") from exc


def extract_content(html: str, page_url: str | None = None):
    return parse_page(html, page_url)


def discover_links(html: str, current_url: str, domain: str):
    soup = _require_bs4()(html, "html.parser")
    links = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(current_url, anchor["href"])
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc == domain and not is_private_host(url):
            links.add(url.split("#", 1)[0])
    return links


class WebsiteCrawler:
    def __init__(self, start_url: str | None = None, max_pages: int = 100, max_depth: int = 3):
        self.start_url = start_url
        self.max_pages = max(1, int(max_pages))
        self.max_depth = max(0, int(max_depth))
        self._robots = None

    async def fetch(self, url: str) -> tuple[str, int]:
        current_url = url
        for _hop in range(MAX_REDIRECTS + 1):
            await assert_safe_url(current_url)
            async with httpx.AsyncClient(timeout=settings.crawler_timeout_seconds, follow_redirects=False) as client:
                response = await client.get(current_url, headers={"User-Agent": "UniversalAI-Bot/1.0"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError(f"Redirect without Location: {current_url}")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            if len(response.content) > settings.crawler_max_page_bytes:
                raise ValueError(f"Page exceeds crawler_max_page_bytes: {current_url}")
            return response.text, response.status_code
        raise ValueError(f"Too many redirects fetching {url}")

    async def _sitemap_urls(self, root: str, domain: str) -> set[str]:
        found = set()
        pending = [urljoin(root, "/sitemap.xml"), urljoin(root, "/sitemap_index.xml")]
        seen = set()
        while pending and len(seen) < 20:
            candidate = pending.pop(0)
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                xml, _ = await self.fetch(candidate)
            except Exception:
                continue
            for url in parse_sitemap(xml):
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or parsed.netloc != domain:
                    continue
                normalized = url.split("#", 1)[0]
                if normalized.endswith(".xml") or "sitemap" in parsed.path.casefold():
                    pending.append(normalized)
                else:
                    found.add(normalized)
        return found

    async def _load_robots(self, root: str):
        rp = robotparser.RobotFileParser()
        robots_url = urljoin(root, "/robots.txt")
        try:
            text, _ = await self.fetch(robots_url)
            rp.parse(text.splitlines())
            self._robots = rp
        except Exception:
            self._robots = None

    def _allowed(self, url: str) -> bool:
        return self._robots is None or self._robots.can_fetch("UniversalAI-Bot/1.0", url)

    async def crawl(self, start_url: str | None = None) -> list[dict]:
        root = start_url or self.start_url
        if not root:
            raise ValueError("WebsiteCrawler.crawl requires a start_url")
        if is_private_host(root):
            raise ValueError(f"Refusing to crawl private/internal address: {root}")
        domain = urlparse(root).netloc
        await self._load_robots(root)
        visited = set()
        queue = deque([(root.split("#", 1)[0], 0)])
        pages = []
        for url in list(await self._sitemap_urls(root, domain))[: self.max_pages]:
            queue.append((url, 1))
        while queue and len(pages) < self.max_pages:
            url, depth = queue.popleft()
            if url in visited or not self._allowed(url):
                continue
            visited.add(url)
            try:
                html, http_status = await self.fetch(url)
            except Exception:
                continue
            extracted = extract_content(html, url)
            pages.append({
                "url": url,
                "title": extracted.get("title"),
                "content": extracted.get("content", ""),
                "http_status": http_status,
                "structured_data": extracted.get("structured_data", []),
            })
            if depth < self.max_depth:
                for link in discover_links(html, url, domain):
                    if link not in visited:
                        queue.append((link, depth + 1))
        return pages
