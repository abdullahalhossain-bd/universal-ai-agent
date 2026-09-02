"""
Platform admin session tokens (JWT).

Issued at admin login, sent back on every admin request as
`Authorization: Bearer <token>`. Completely separate credential from:
- Widget's `x-api-key`
- Dashboard user JWT (from app/auth/jwt_session.py)

The token carries only the admin id (`sub`); `get_current_admin`
(app/auth/admin_auth.py) re-fetches the admin row from the DB on every
request rather than trusting any claim, so a token can't outlive a
deleted admin or smuggle stale data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

_ALGORITHM_ALLOWLIST = ["HS256"]


class InvalidAdminSessionToken(Exception):
    pass


def create_admin_access_token(*, admin_id: str) -> str:
    """
    Issue a new admin JWT.

    Tokens expire independently from dashboard user sessions. A
    stolen admin token must not grant indefinite access.
    """

    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_jwt_access_token_minutes),
        "type": "platform_admin_session",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_admin_access_token(token: str) -> dict:
    """
    Decode and validate an admin JWT.

    Raises InvalidAdminSessionToken if the token is malformed,
    expired (if exp is added), or has the wrong type.
    """

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=_ALGORITHM_ALLOWLIST,
        )
    except jwt.PyJWTError as exc:
        raise InvalidAdminSessionToken(str(exc)) from exc

    if payload.get("type") != "platform_admin_session":
        # Belt-and-suspenders: never accept a token minted for
        # some other purpose even if it's otherwise validly signed.
        raise InvalidAdminSessionToken("wrong token type")

    return payload
