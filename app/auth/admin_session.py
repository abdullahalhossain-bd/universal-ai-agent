"""Platform admin session JWT creation and decoding."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import jwt
from app.core.config import settings

_ALGORITHM_ALLOWLIST = ["HS256"]
class InvalidAdminSessionToken(Exception):
    pass

def create_admin_access_token(*, admin_id: str, session_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin_id,
        "session_version": int(session_version),
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_jwt_access_token_minutes),
        "type": "platform_admin_session",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def decode_admin_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=_ALGORITHM_ALLOWLIST)
    except jwt.PyJWTError as exc:
        raise InvalidAdminSessionToken(str(exc)) from exc
    if payload.get("type") != "platform_admin_session" or "session_version" not in payload:
        raise InvalidAdminSessionToken("invalid admin session claims")
    return payload
