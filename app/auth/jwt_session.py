"""
Dashboard session tokens (JWT).

Issued at login/signup, sent back on every dashboard request as
`Authorization: Bearer <token>`. Completely separate credential from
the widget's `x-api-key` — see app/db/models.py's `User` docstring.
The token carries only the user id (`sub`) and store id (`store_id`);
`get_current_user` (app/auth/dashboard_auth.py) re-fetches both rows
from the DB on every request rather than trusting any other claim, so
a token can't outlive a deleted user/store or smuggle stale data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

_ALGORITHM_ALLOWLIST = ["HS256"]


class InvalidSessionToken(Exception):
    pass


def create_access_token(*, user_id: str, store_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "store_id": store_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_minutes),
        "type": "dashboard_session",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=_ALGORITHM_ALLOWLIST,
        )
    except jwt.PyJWTError as exc:
        raise InvalidSessionToken(str(exc)) from exc

    if payload.get("type") != "dashboard_session":
        # Belt-and-suspenders: never accept a token minted for some
        # other purpose even if it's otherwise validly signed.
        raise InvalidSessionToken("wrong token type")

    return payload
