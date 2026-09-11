"""Dashboard authentication and dedicated Merchant Inbox session endpoints."""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.dashboard_auth import get_current_user
from app.auth.inbox_auth import (
    clear_inbox_cookies,
    get_current_inbox_user_and_store,
    issue_csrf_token,
    require_inbox_csrf,
    set_inbox_cookies,
)
from app.auth.jwt_session import create_access_token
from app.auth.password import WeakPasswordError, hash_password, verify_password
from app.billing.plans import plan_budgets
from app.core.security import generate_api_key, resolve_client_ip
from app.core.rate_limit import enforce_login_rate_limit, enforce_signup_rate_limit
from app.db.database import get_db
from app.db.models import APIKey, Store, User

router = APIRouter(prefix="/v1/auth", tags=["auth"])

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    store_name: str = Field(min_length=1, max_length=255)
    website_url: str | None = None
    plan: str = "starter"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    store: dict
    api_key: str | None = None

def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}

def _store_dict(store: Store) -> dict:
    return {"id": store.id, "name": store.name, "website_url": store.website_url, "plan": store.plan, "monthly_budget": float(store.monthly_budget), "status": store.status}

def _client_ip(request: Request) -> str:
    return resolve_client_ip(peer_host=request.client.host if request.client else None, forwarded_for=request.headers.get("x-forwarded-for"))

@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(payload: SignupRequest, http_request: Request, db: Session = Depends(get_db)):
    await enforce_signup_rate_limit(client_ip=_client_ip(http_request))
    plan_name = payload.plan.lower().strip()
    budgets = plan_budgets(db)
    if plan_name not in budgets:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Use one of: {', '.join(budgets)}.")
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    try:
        password_hash = hash_password(payload.password)
    except WeakPasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store = Store(name=payload.store_name, website_url=payload.website_url, plan=plan_name, monthly_budget=budgets[plan_name])
    db.add(store); db.flush()
    user = User(store_id=store.id, email=payload.email.lower(), password_hash=password_hash)
    db.add(user)
    raw_key, prefix, key_hash = generate_api_key()
    db.add(APIKey(store_id=store.id, key_prefix=prefix, key_hash=key_hash, name="Default Key"))
    db.commit(); db.refresh(user); db.refresh(store)
    token = create_access_token(user_id=user.id, store_id=store.id, session_version=user.session_version)
    return AuthResponse(access_token=token, user=_user_dict(user), store=_store_dict(store), api_key=raw_key)

@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    await enforce_login_rate_limit(client_ip=_client_ip(http_request), email=payload.email)
    generic_error = HTTPException(status_code=401, detail="Invalid email or password")
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        verify_password(payload.password, "$2b$12$" + "0" * 53)
        raise generic_error
    if not verify_password(payload.password, user.password_hash):
        raise generic_error
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise generic_error
    user.last_login_at = datetime.utcnow(); db.add(user); db.commit()
    token = create_access_token(user_id=user.id, store_id=store.id, session_version=user.session_version)
    return AuthResponse(access_token=token, user=_user_dict(user), store=_store_dict(store))

@router.post("/inbox/login")
async def inbox_login(payload: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    """Create a browser-only Merchant Inbox session without exposing a JWT to JS."""
    await enforce_login_rate_limit(client_ip=_client_ip(http_request), email=payload.email)
    generic_error = HTTPException(status_code=401, detail="Invalid email or password")
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        verify_password(payload.password, "$2b$12$" + "0" * 53)
        raise generic_error
    if not verify_password(payload.password, user.password_hash):
        raise generic_error
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None or store.status == "suspended":
        raise generic_error
    user.last_login_at = datetime.utcnow(); db.add(user); db.commit()
    token = create_access_token(user_id=user.id, store_id=store.id, session_version=user.session_version)
    response = JSONResponse({"ok": True, "user": _user_dict(user), "store": _store_dict(store)})
    set_inbox_cookies(response, token, issue_csrf_token())
    return response

@router.get("/inbox/me")
async def inbox_me(auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store)):
    user, store = auth
    return {"user": _user_dict(user), "store": _store_dict(store)}

@router.post("/inbox/logout")
async def inbox_logout(
    auth: tuple[User, Store] = Depends(get_current_inbox_user_and_store),
    _csrf: None = Depends(require_inbox_csrf),
    db: Session = Depends(get_db),
):
    user, _store = auth
    user.session_version += 1; db.add(user); db.commit()
    response = JSONResponse({"ok": True}); clear_inbox_cookies(response); return response

@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke all currently issued dashboard tokens for this user."""
    user.session_version += 1
    db.add(user); db.commit()
    return {"ok": True}

@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"user": _user_dict(user), "store": _store_dict(store)}
