import socket

import pytest
from fastapi import HTTPException
from starlette.requests import Request


@pytest.mark.asyncio
async def test_crawler_rejects_dns_resolution_to_private_ip(monkeypatch):
    from app.knowledge import crawler

    monkeypatch.setattr(crawler, "_local_hosts_allowed", lambda: False)
    monkeypatch.setattr(
        crawler.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.8", 443))
        ],
    )

    with pytest.raises(ValueError, match="private/internal"):
        await crawler.assert_safe_url("https://public-example.test/")


@pytest.mark.asyncio
async def test_pinned_resolver_returns_validated_public_ip(monkeypatch):
    from app.knowledge import crawler

    monkeypatch.setattr(crawler, "_local_hosts_allowed", lambda: False)
    monkeypatch.setattr(
        crawler.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ],
    )

    resolver = crawler._PinnedResolver()
    resolved = await resolver.resolve("example.test", 443)
    await resolver.close()

    assert resolved[0]["hostname"] == "example.test"
    assert resolved[0]["host"] == "93.184.216.34"
    assert resolved[0]["port"] == 443
    assert resolved[0]["proto"] == socket.IPPROTO_TCP


@pytest.mark.asyncio
async def test_customer_rate_limit_uses_atomic_redis_script(monkeypatch):
    from app.core import customer_rate_limit

    calls = []

    class FakeRedis:
        async def eval(self, script, numkeys, key, window):
            calls.append((script, numkeys, key, window))
            return 1

    monkeypatch.setattr(customer_rate_limit, "redis_client", FakeRedis())
    assert await customer_rate_limit._hit("bucket:test", 5, 60) is False
    assert calls and calls[0][1:] == (1, "bucket:test", 60)
    assert "INCR" in calls[0][0] and "EXPIRE" in calls[0][0]


@pytest.mark.asyncio
async def test_customer_rate_limit_fails_closed_for_state_changes(monkeypatch):
    from app.core import customer_rate_limit

    class BrokenRedis:
        async def eval(self, *args, **kwargs):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(customer_rate_limit, "redis_client", BrokenRedis())
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/messages/customer/conversation/mode",
        "headers": [(b"x-api-key", b"public-key")],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
        "query_string": b"",
        "root_path": "",
        "http_version": "1.1",
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc:
        await customer_rate_limit.enforce_customer_rate_limit(request)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_customer_rate_limit_does_not_use_shared_anonymous_visitor_bucket(monkeypatch):
    from app.core import customer_rate_limit

    buckets = []

    async def fake_hit(bucket, limit, window_seconds=60):
        buckets.append(bucket)
        return False

    monkeypatch.setattr(customer_rate_limit, "_hit", fake_hit)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/messages/customer/conversation",
        "headers": [(b"x-api-key", b"public-key")],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
        "query_string": b"",
        "root_path": "",
        "http_version": "1.1",
    }
    await customer_rate_limit.enforce_customer_rate_limit(Request(scope))

    assert all("customer-rate:visitor:" not in bucket for bucket in buckets)
    assert any(bucket.startswith("customer-rate:ip:") for bucket in buckets)
    assert any(bucket.startswith("customer-rate:api:") for bucket in buckets)
