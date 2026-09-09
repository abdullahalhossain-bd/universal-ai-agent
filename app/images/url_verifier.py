"""Safe, bounded verification for merchant-supplied product image URLs."""
from __future__ import annotations
import asyncio,time
from collections import OrderedDict
from urllib.parse import urljoin,urlparse
import httpx
from app.core.network_guard import assert_safe_http_url
_CACHE_TTL_SECONDS=600.0;_CACHE_MAX_ENTRIES=2048;_TIMEOUT=httpx.Timeout(4.0,connect=2.0);_MAX_PROBE_BYTES=32;_ALLOWED_IMAGE_TYPES=frozenset({"image/jpeg","image/png","image/webp","image/gif"})
_cache:OrderedDict[str,tuple[float,bool]]=OrderedDict();_inflight:dict[str,asyncio.Task[bool]]={}
def _cache_get(url):
 entry=_cache.get(url)
 if entry is None:return None
 expires,value=entry
 if expires<=time.monotonic():_cache.pop(url,None);return None
 _cache.move_to_end(url);return value
def _cache_put(url,value):
 _cache[url]=(time.monotonic()+_CACHE_TTL_SECONDS,value);_cache.move_to_end(url)
 while len(_cache)>_CACHE_MAX_ENTRIES:_cache.popitem(last=False)
def _looks_like_image(content_type,prefix):
 mime=(content_type or "").split(";",1)[0].strip().lower()
 if mime not in _ALLOWED_IMAGE_TYPES:return False
 if mime=="image/jpeg":return prefix.startswith(b"\xff\xd8\xff")
 if mime=="image/png":return prefix.startswith(b"\x89PNG\r\n\x1a\n")
 if mime=="image/webp":return len(prefix)>=12 and prefix[:4]==b"RIFF" and prefix[8:12]==b"WEBP"
 if mime=="image/gif":return prefix.startswith((b"GIF87a",b"GIF89a"))
 return False
async def _probe(url):
 try:
  parsed=urlparse(url)
  if parsed.scheme not in {"http","https"} or not parsed.netloc:return False
  current=url
  async with httpx.AsyncClient(timeout=_TIMEOUT,follow_redirects=False,headers={"User-Agent":"UniversalCommerceAI/1.1 image-verifier"}) as client:
   for _ in range(4):
    assert_safe_http_url(current)
    async with client.stream("GET",current) as response:
     if 200<=response.status_code<300:
      content_type=response.headers.get("content-type","")
      if not content_type.lower().startswith("image/"):return False
      prefix=await response.aiter_bytes().__anext__()
      return _looks_like_image(content_type,prefix[:_MAX_PROBE_BYTES])
     if response.status_code not in {301,302,303,307,308}:return False
     location=response.headers.get("location")
     if not location:return False
     current=urljoin(current,location)
  return False
 except(httpx.HTTPError,ValueError,StopAsyncIteration,OSError):return False
async def verify_image_url(url):
 if not isinstance(url,str) or not url.strip():return False
 normalized=url.strip();cached=_cache_get(normalized)
 if cached is not None:return cached
 task=_inflight.get(normalized)
 if task is None:task=asyncio.create_task(_probe(normalized));_inflight[normalized]=task
 try:
  value=await task;_cache_put(normalized,value);return value
 finally:
  if _inflight.get(normalized) is task:_inflight.pop(normalized,None)
async def verify_image_urls(urls):
 unique=list(dict.fromkeys(url.strip() for url in urls if isinstance(url,str) and url.strip()))
 if not unique:return {}
 results=await asyncio.gather(*(verify_image_url(url) for url in unique));return dict(zip(unique,results))
def clear_image_verification_cache():
 _cache.clear();_inflight.clear()
