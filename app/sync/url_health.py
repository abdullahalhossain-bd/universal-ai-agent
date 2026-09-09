"""Bounded product URL health verification with SSRF protection and caching."""
from __future__ import annotations
import asyncio
import time
from urllib.parse import urlparse
import httpx
from app.core.url_security import assert_safe_http_url

_CACHE: dict[str, tuple[float, bool]] = {}
_LOCK = asyncio.Lock()
_TTL = 600.0
_MAX = 2048

async def verify_product_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip(): return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: return False
        assert_safe_http_url(url.strip())
    except Exception: return False
    key=url.strip()
    now=time.monotonic()
    cached=_CACHE.get(key)
    if cached and cached[0] > now: return cached[1]
    try:
        timeout=httpx.Timeout(4.0, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=3, headers={"User-Agent":"Universal-AI-Agent-URL-Health/1.0"}) as client:
            async with client.stream("GET", key) as response:
                ok=200 <= response.status_code < 400
    except Exception: ok=False
    _CACHE[key]=(now+_TTL,ok)
    if len(_CACHE)>_MAX:
        oldest=min(_CACHE,key=lambda k:_CACHE[k][0]); _CACHE.pop(oldest,None)
    return ok

async def verify_product_urls(urls: list[str], *, concurrency: int = 20) -> dict[str,bool]:
    unique=list(dict.fromkeys(u.strip() for u in urls if isinstance(u,str) and u.strip()))
    sem=asyncio.Semaphore(max(1,min(concurrency,50)))
    async def one(url):
        async with sem: return url, await verify_product_url(url)
    results=await asyncio.gather(*(one(u) for u in unique), return_exceptions=False)
    return dict(results)
