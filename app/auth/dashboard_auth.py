"""Dashboard auth dependency — Authorization: Bearer <JWT>."""

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
    if not isinstance(credentials, HTTPAuthorizationCredentials):
        credentials = None
    if credentials is None and authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2:
            credentials = HTTPAuthorizationCredentials(scheme=parts[0], credentials=parts[1])
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
    if user is None or int(payload["session_version"]) != int(user.session_version):
        raise HTTPException(status_code=401, detail="Invalid or revoked session")
    return user


async def get_current_user_and_store(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[User, Store]:
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise HTTPException(status_code=401, detail="Store not found")
    if store.status == "suspended":
        raise HTTPException(status_code=403, detail="This store has been suspended. Contact support.")
    return user, store


async def is_dashboard_request_for_store(http_request, db: Session, store: Store) -> bool:
    """Return True only when the Bearer credential is a valid merchant JWT for this store.

    Do not infer dashboard identity from the mere presence of an Authorization
    header: a request carrying both a valid Bearer JWT and a public x-api-key
    (proxy injection, merchant pasting the widget key) must still resolve
    correctly, and a JWT belonging to a *different* merchant must never
    bypass this store's public conversation-token requirement. Shared by
    /v1/chat and /v1/images so both use one consistent rule.
    """
    authorization = http_request.headers.get("authorization")
    if not authorization:
        return False
    try:
        user = await get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return False
    return str(user.store_id) == str(store.id)
