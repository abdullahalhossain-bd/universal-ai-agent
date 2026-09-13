"""Platform-admin auth dependency."""
from __future__ import annotations
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.auth.admin_session import InvalidAdminSessionToken, decode_admin_access_token
from app.db.database import get_db
from app.db.models import PlatformAdmin

async def get_current_admin(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db),
) -> PlatformAdmin:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin session token required")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Admin session token required")
    try:
        payload = decode_admin_access_token(token)
    except InvalidAdminSessionToken:
        raise HTTPException(status_code=401, detail="Invalid or expired admin session")
    admin = db.query(PlatformAdmin).filter(PlatformAdmin.id == payload["sub"]).first()
    if admin is None or int(payload["session_version"]) != int(admin.session_version):
        raise HTTPException(status_code=401, detail="Invalid or revoked admin session")
    return admin
