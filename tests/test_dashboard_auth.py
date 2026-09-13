"""
Dashboard auth: password hashing, JWT session tokens, and the
signup/login HTTP flow. The HTTP-level tests need a real Postgres
(the `User`/`Store` rows have to actually persist) so they're gated
like the rest of the DB-backed suite; the pure password/JWT unit
tests run everywhere.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from tests.markers import requires_postgres, skip_unless_postgres


# ---------------------------------------------------------------------------
# Password hashing (no DB needed)
# ---------------------------------------------------------------------------


def test_hash_and_verify_roundtrip():
    from app.auth.password import hash_password, verify_password

    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_hash_password_rejects_short_password():
    from app.auth.password import WeakPasswordError, hash_password

    with pytest.raises(WeakPasswordError):
        hash_password("short")


def test_verify_password_never_raises_on_garbage_hash():
    from app.auth.password import verify_password

    # A malformed/legacy hash must fail closed, not 500.
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


# ---------------------------------------------------------------------------
# JWT session tokens (no DB needed)
# ---------------------------------------------------------------------------


def test_access_token_roundtrip():
    from app.auth.jwt_session import create_access_token, decode_access_token

    token = create_access_token(user_id="user-1", store_id="store-1")
    payload = decode_access_token(token)

    assert payload["sub"] == "user-1"
    assert payload["store_id"] == "store-1"
    assert payload["type"] == "dashboard_session"


def test_decode_rejects_tampered_token():
    from app.auth.jwt_session import InvalidSessionToken, decode_access_token

    with pytest.raises(InvalidSessionToken):
        decode_access_token("not.a.real.token")


def test_decode_rejects_token_signed_with_a_different_secret():
    import jwt as pyjwt

    from app.auth.jwt_session import InvalidSessionToken, decode_access_token

    forged = pyjwt.encode(
        {"sub": "attacker", "store_id": "victim-store", "type": "dashboard_session"},
        "some-other-secret",
        algorithm="HS256",
    )
    with pytest.raises(InvalidSessionToken):
        decode_access_token(forged)


def test_get_current_user_rejects_missing_authorization_header():
    import asyncio

    from app.auth.dashboard_auth import get_current_user

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(authorization=None, db=None))
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_non_bearer_header():
    import asyncio

    from app.auth.dashboard_auth import get_current_user

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(authorization="Basic abc123", db=None))
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# HTTP-level signup/login (needs Postgres — persists User/Store rows)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    skip_unless_postgres()
    from app.db.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@requires_postgres
def test_signup_creates_user_store_and_api_key(client, db_session):
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "store_name": "Test Shop",
            "plan": "starter",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["api_key"].startswith("pk_live_")
    assert body["store"]["name"] == "Test Shop"
    assert body["user"]["email"] == email


@requires_postgres
def test_signup_rejects_duplicate_email(client):
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "correct horse battery staple",
        "store_name": "Shop One",
    }
    first = client.post("/v1/auth/signup", json=payload)
    assert first.status_code == 201

    second = client.post(
        "/v1/auth/signup",
        json={**payload, "store_name": "Shop Two"},
    )
    assert second.status_code == 409


@requires_postgres
def test_login_succeeds_with_correct_password_and_fails_with_wrong_one(client):
    email = f"login-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/v1/auth/signup",
        json={"email": email, "password": "correct horse battery staple", "store_name": "Shop"},
    )

    ok = client.post(
        "/v1/auth/login", json={"email": email, "password": "correct horse battery staple"}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post("/v1/auth/login", json={"email": email, "password": "wrong password"})
    assert bad.status_code == 401


@requires_postgres
def test_login_with_unknown_email_gives_same_generic_error(client):
    resp = client.post(
        "/v1/auth/login",
        json={"email": "nobody-here@example.com", "password": "whatever12345"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


@requires_postgres
def test_me_requires_session_token_and_returns_own_store(client):
    email = f"me-{uuid.uuid4().hex[:8]}@example.com"
    signup = client.post(
        "/v1/auth/signup",
        json={"email": email, "password": "correct horse battery staple", "store_name": "My Shop"},
    )
    token = signup.json()["access_token"]

    unauth = client.get("/v1/auth/me")
    assert unauth.status_code == 401

    authed = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200
    assert authed.json()["store"]["name"] == "My Shop"


@requires_postgres
def test_dashboard_session_can_reach_store_scoped_routes_without_api_key(client):
    """
    app.core.tenant.get_current_store must accept a dashboard
    Authorization: Bearer token as an alternative to x-api-key —
    this is what lets the React dashboard call datasource/discovery/
    mapping/billing routes using only the login session.
    """
    email = f"dual-{uuid.uuid4().hex[:8]}@example.com"
    signup = client.post(
        "/v1/auth/signup",
        json={"email": email, "password": "correct horse battery staple", "store_name": "Dual Auth Shop"},
    )
    token = signup.json()["access_token"]

    resp = client.get(
        "/v1/stores/me/api-keys", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["api_keys"]) == 1  # the signup-issued default key


@requires_postgres
def test_two_stores_dashboard_sessions_cannot_see_each_others_api_keys(client):
    def _signup():
        email = f"iso-{uuid.uuid4().hex[:8]}@example.com"
        r = client.post(
            "/v1/auth/signup",
            json={"email": email, "password": "correct horse battery staple", "store_name": "Shop"},
        )
        return r.json()["access_token"], r.json()["store"]["id"]

    token_a, store_a_id = _signup()
    token_b, store_b_id = _signup()

    keys_a = client.get(
        "/v1/stores/me/api-keys", headers={"Authorization": f"Bearer {token_a}"}
    ).json()["api_keys"]
    keys_b = client.get(
        "/v1/stores/me/api-keys", headers={"Authorization": f"Bearer {token_b}"}
    ).json()["api_keys"]

    ids_a = {k["id"] for k in keys_a}
    ids_b = {k["id"] for k in keys_b}
    assert ids_a.isdisjoint(ids_b)

    # Revoking store B's key via store A's session must 404, not succeed.
    victim_key_id = keys_b[0]["id"]
    resp = client.post(
        f"/v1/stores/me/api-keys/{victim_key_id}/revoke",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404
