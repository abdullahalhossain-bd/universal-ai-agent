"""
Dashboard auth dependency — `Authorization: Bearer <jwt>`.

Uses FastAPI's HTTPBearer security dependency so the Authorization
header is represented correctly in OpenAPI/Swagger UI. The optional
raw `authorization` argument is retained for direct/unit callers.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt_session import InvalidSessionToken, decode_access_token
from app.db.database import get_db
from app.db.models import Store, User


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, include_in_schema=False),
) -> User:
    # When FastAPI resolves this dependency, `credentials` is either None or
    # an HTTPAuthorizationCredentials instance. Direct/unit callers may invoke
    # the function without FastAPI resolving Depends(), so normalize that case
    # through the explicit raw Authorization header instead of dereferencing
    # the Depends sentinel.
    if not isinstance(credentials, HTTPAuthorizationCredentials):
        credentials = None

    if credentials is None and authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2:
            credentials = HTTPAuthorizationCredentials(
                scheme=parts[0], credentials=parts[1]
            )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Session token required")

    token = credentials.credentials.strip()
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
