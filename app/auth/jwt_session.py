"""Dashboard session JWT creation and decoding."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
import jwt
from app.core.config import settings

_ALGORITHM_ALLOWLIST = ["HS256"]

class InvalidSessionToken(Exception):
    pass


def create_access_token(*, user_id: str, store_id: str, session_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "store_id": store_id,
        "session_version": int(session_version),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_minutes),
        "type": "dashboard_session",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=_ALGORITHM_ALLOWLIST)
    except jwt.PyJWTError as exc:
        raise InvalidSessionToken(str(exc)) from exc
    if payload.get("type") != "dashboard_session":
        raise InvalidSessionToken("wrong token type")
    if "sub" not in payload or "store_id" not in payload or "session_version" not in payload:
        raise InvalidSessionToken("missing session claims")
    return payload
