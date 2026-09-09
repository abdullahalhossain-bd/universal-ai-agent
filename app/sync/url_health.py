"""Bounded product URL health verification with basic SSRF protection and caching."""
from __future__ import annotations
import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlparse
import httpx

_CACHE: dict[str, tuple[float, bool]] = {}
_TTL = 600.0
_MAX = 2048


def _safe_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        except ValueError:
            return False
    return bool(infos)

async def verify_product_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip(): return False
    key=url.strip()
    try:
        parsed=urlparse(key)
        if parsed.scheme.casefold() not in {"http","https"} or not parsed.hostname or not _safe_host(parsed.hostname): return False
    except Exception: return False
    now=time.monotonic(); cached=_CACHE.get(key)
    if cached and cached[0]>now: return cached[1]
    try:
        timeout=httpx.Timeout(4.0,connect=2.0)
        async with httpx.AsyncClient(timeout=timeout,follow_redirects=True,max_redirects=3,headers={"User-Agent":"Universal-AI-Agent-URL-Health/1.0"}) as client:
            async with client.stream("GET",key) as response:
                ok=200<=response.status_code<400
                final=response.url
                if ok and final.hostname and not _safe_host(final.hostname): ok=False
    except Exception: ok=False
    _CACHE[key]=(now+_TTL,ok)
    if len(_CACHE)>_MAX:
        oldest=min(_CACHE,key=lambda k:_CACHE[k][0]); _CACHE.pop(oldest,None)
    return ok

async def verify_product_urls(urls: list[str], *, concurrency: int=20) -> dict[str,bool]:
    unique=list(dict.fromkeys(u.strip() for u in urls if isinstance(u,str) and u.strip()))
    sem=asyncio.Semaphore(max(1,min(concurrency,50)))
    async def one(url):
        async with sem: return url,await verify_product_url(url)
    return dict(await asyncio.gather(*(one(u) for u in unique)))
