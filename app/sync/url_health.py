"""Bounded product URL health verification with SSRF-safe redirects and caching."""
from __future__ import annotations
import asyncio,ipaddress,socket,time
from urllib.parse import urljoin,urlparse
import httpx
_CACHE:dict[str,tuple[float,bool]]={};_TTL=600.0;_MAX=2048

def _safe_host(host:str)->bool:
    try:infos=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
    except OSError:return False
    for info in infos:
        try:
            ip=ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:return False
        except ValueError:return False
    return bool(infos)

def _safe_url(url:str)->bool:
    try:
        parsed=urlparse(url)
        return parsed.scheme.casefold() in {"http","https"} and bool(parsed.hostname) and _safe_host(parsed.hostname)
    except Exception:return False

async def verify_product_url(url:str)->bool:
    if not isinstance(url,str) or not url.strip():return False
    key=url.strip();now=time.monotonic();cached=_CACHE.get(key)
    if cached and cached[0]>now:return cached[1]
    ok=False
    try:
        if not _safe_url(key):return False
        current=key
        timeout=httpx.Timeout(4.0,connect=2.0)
        async with httpx.AsyncClient(timeout=timeout,follow_redirects=False,headers={"User-Agent":"Universal-AI-Agent-URL-Health/1.1"}) as client:
            for _ in range(4):
                if not _safe_url(current):break
                async with client.stream("GET",current) as response:
                    if 200<=response.status_code<400 and response.status_code not in {301,302,303,307,308}:
                        ok=True;break
                    if response.status_code not in {301,302,303,307,308}:break
                    location=response.headers.get("location")
                    if not location:break
                    current=urljoin(current,location)
    except Exception:ok=False
    _CACHE[key]=(time.monotonic()+_TTL,ok)
    while len(_CACHE)>_MAX:_CACHE.pop(next(iter(_CACHE)))
    return ok

async def verify_product_urls(urls:list[str],*,concurrency:int=20)->dict[str,bool]:
    unique=list(dict.fromkeys(u.strip() for u in urls if isinstance(u,str) and u.strip()));sem=asyncio.Semaphore(max(1,min(concurrency,50)))
    async def one(url):
        async with sem:return url,await verify_product_url(url)
    return dict(await asyncio.gather(*(one(u) for u in unique)))
