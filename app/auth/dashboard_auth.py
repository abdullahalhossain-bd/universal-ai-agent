"""
Dashboard auth dependency — `Authorization: Bearer <jwt>`.

Mirrors app.auth.api_key.get_api_key's shape (fail fast on a missing
header, look the row up fresh from the DB, 401 on anything that
doesn't check out) but for `User` sessions instead of `APIKey`s.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt_session import InvalidSessionToken, decode_access_token
from app.db.database import get_db
from app.db.models import Store, User


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Session token required")

    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Session token required")

    try:
        payload = decode_access_token(token)
    except InvalidSessionToken:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return user


async def get_current_user_and_store(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[User, Store]:
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise HTTPException(status_code=401, detail="Store not found")
    return user, store
