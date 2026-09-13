import pytest
from types import SimpleNamespace

from app.chat import router


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _Request:
    def __init__(self, **headers):
        self.headers = _Headers({key.lower(): value for key, value in headers.items()})


class _DB:
    pass


@pytest.mark.asyncio
async def test_dashboard_request_requires_valid_jwt_for_same_store(monkeypatch):
    async def fake_get_current_user(*, authorization, db):
        assert authorization == "Bearer merchant-jwt"
        return SimpleNamespace(store_id="store-1")

    monkeypatch.setattr("app.auth.dashboard_auth.get_current_user", fake_get_current_user)

    result = await router._is_authenticated_dashboard_request(
        _Request(Authorization="Bearer merchant-jwt", **{"x-api-key": "pk_live_public"}),
        _DB(),
        SimpleNamespace(id="store-1"),
    )

    assert result is True


@pytest.mark.asyncio
async def test_wrong_store_jwt_does_not_bypass_conversation_token(monkeypatch):
    async def fake_get_current_user(*, authorization, db):
        return SimpleNamespace(store_id="store-2")

    monkeypatch.setattr("app.auth.dashboard_auth.get_current_user", fake_get_current_user)

    result = await router._is_authenticated_dashboard_request(
        _Request(Authorization="Bearer merchant-jwt"),
        _DB(),
        SimpleNamespace(id="store-1"),
    )

    assert result is False


@pytest.mark.asyncio
async def test_missing_jwt_is_customer_path(monkeypatch):
    called = False

    async def fake_get_current_user(*, authorization, db):
        nonlocal called
        called = True
        return SimpleNamespace(store_id="store-1")

    monkeypatch.setattr("app.auth.dashboard_auth.get_current_user", fake_get_current_user)

    result = await router._is_authenticated_dashboard_request(
        _Request(),
        _DB(),
        SimpleNamespace(id="store-1"),
    )

    assert result is False
    assert called is False


@pytest.mark.asyncio
async def test_invalid_jwt_does_not_bypass_conversation_token(monkeypatch):
    from fastapi import HTTPException

    async def fake_get_current_user(*, authorization, db):
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr("app.auth.dashboard_auth.get_current_user", fake_get_current_user)

    result = await router._is_authenticated_dashboard_request(
        _Request(Authorization="Bearer invalid"),
        _DB(),
        SimpleNamespace(id="store-1"),
    )

    assert result is False
