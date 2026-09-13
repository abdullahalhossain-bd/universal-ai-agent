"""Dedicated cookie-based authentication for the merchant inbox.

The public widget key is never accepted here.  Inbox sessions use the same
signed dashboard JWT format, but keep the JWT in an HttpOnly cookie and use a
separate CSRF cookie/header pair for state-changing requests.
"""

from __future__ import annotations

import secrets
import hmac

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.jwt_session import InvalidSessionToken, decode_access_token
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Store, User

INBOX_SESSION_COOKIE = "ucai_merchant_session"
INBOX_CSRF_COOKIE = "ucai_merchant_csrf"


def _invalid_session() -> HTTPException:
    return HTTPException(status_code=401, detail="Inbox session required")


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


async def get_current_inbox_user(
    session_token: str | None = Cookie(default=None, alias=INBOX_SESSION_COOKIE),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    # Prefer the Authorization header: on cross-origin dashboard deployments
    # (dashboard and API on different domains) the HttpOnly session cookie
    # can't be sent, since the API's CORS policy is wildcard (required for
    # the embeddable widget on arbitrary storefront domains), and browsers
    # refuse wildcard-origin + credentialed requests together. The dashboard
    # already sends its normal Bearer token on every request, and it's the
    # same signed JWT the cookie carries, so accept either.
    token = _bearer_token(authorization) or (session_token.strip() if session_token else None)
    if not token:
        raise _invalid_session()
    try:
        payload = decode_access_token(token)
    except InvalidSessionToken:
        raise _invalid_session()

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None:
        raise _invalid_session()
    try:
        valid_version = int(payload["session_version"]) == int(user.session_version)
    except (KeyError, TypeError, ValueError):
        valid_version = False
    if not valid_version:
        raise HTTPException(status_code=401, detail="Inbox session revoked")
    return user


async def get_current_inbox_user_and_store(
    user: User = Depends(get_current_inbox_user),
    db: Session = Depends(get_db),
) -> tuple[User, Store]:
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise HTTPException(status_code=401, detail="Store not found")
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="This store has been suspended. Contact support.")
    return user, store


async def require_inbox_csrf(
    request: Request,
    csrf_cookie: str | None = Cookie(default=None, alias=INBOX_CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="x-csrf-token"),
    authorization: str | None = Header(default=None),
) -> None:
    """Require a double-submit CSRF token for inbox state changes.

    Skipped when the request used a Bearer token: CSRF exploits rely on the
    browser attaching credentials (cookies) automatically to a forged
    request; a Bearer header is never sent that way, so there's nothing for
    the double-submit check to protect against in that case.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if _bearer_token(authorization):
        return
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_inbox_cookies(response, session_token: str, csrf_token: str) -> None:
    secure = settings.environment.lower().strip() in {"production", "prod"} or settings.app_env.lower().strip() in {"production", "prod"}
    response.set_cookie(
        key=INBOX_SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.jwt_access_token_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=INBOX_CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=settings.jwt_access_token_minutes * 60,
        path="/",
    )


def clear_inbox_cookies(response) -> None:
    response.delete_cookie(INBOX_SESSION_COOKIE, path="/")
    response.delete_cookie(INBOX_CSRF_COOKIE, path="/")
