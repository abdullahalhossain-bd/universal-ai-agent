from __future__ import annotations

import uuid

from tests.markers import requires_postgres


PASSWORD = "correct horse battery staple"


@requires_postgres
def test_logout_revokes_existing_dashboard_token(client):
    email = f"logout-{uuid.uuid4().hex[:10]}@example.com"
    signup = client.post(
        "/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "store_name": "Logout Shop"},
    )
    assert signup.status_code == 201, signup.text
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/v1/auth/me", headers=headers).status_code == 200
    logged_out = client.post("/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 200
    assert logged_out.json() == {"ok": True}

    after = client.get("/v1/auth/me", headers=headers)
    assert after.status_code == 401
    assert "revoked" in after.json()["detail"].lower()


@requires_postgres
def test_logout_revokes_all_tokens_issued_before_logout(client):
    email = f"multi-session-{uuid.uuid4().hex[:10]}@example.com"
    signup = client.post(
        "/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "store_name": "Session Shop"},
    )
    assert signup.status_code == 201
    first_token = signup.json()["access_token"]

    second = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert second.status_code == 200
    second_token = second.json()["access_token"]

    first_headers = {"Authorization": f"Bearer {first_token}"}
    second_headers = {"Authorization": f"Bearer {second_token}"}
    assert client.get("/v1/auth/me", headers=second_headers).status_code == 200

    assert client.post("/v1/auth/logout", headers=first_headers).status_code == 200
    assert client.get("/v1/auth/me", headers=first_headers).status_code == 401
    assert client.get("/v1/auth/me", headers=second_headers).status_code == 401


def test_access_token_contains_session_version():
    from app.auth.jwt_session import create_access_token, decode_access_token

    token = create_access_token(user_id="user-1", store_id="store-1", session_version=7)
    payload = decode_access_token(token)
    assert payload["session_version"] == 7
