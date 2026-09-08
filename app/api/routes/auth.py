"""
Dashboard authentication: signup (creates Store + User + first API
key together), login, and "who am I". Entirely separate from the
widget's x-api-key auth — see app/db/models.py's User docstring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.dashboard_auth import get_current_user
from app.auth.jwt_session import create_access_token
from app.auth.password import (
    WeakPasswordError,
    hash_password,
    verify_password,
)
from app.billing.plans import PLAN_BUDGETS
from app.core.security import generate_api_key
from app.core.security import resolve_client_ip
from app.core.rate_limit import enforce_signup_rate_limit
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
    # Only ever present on signup — the raw widget API key is shown
    # exactly once and never retrievable again (only its hash is
    # stored). See app/api/routes/api_keys.py to issue more later.
    api_key: str | None = None


def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}


def _store_dict(store: Store) -> dict:
    return {
        "id": store.id,
        "name": store.name,
        "website_url": store.website_url,
        "plan": store.plan,
        "monthly_budget": float(store.monthly_budget),
        "status": store.status,
    }


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(
    payload: SignupRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    client_ip = resolve_client_ip(
        peer_host=(
            http_request.client.host
            if http_request.client
            else None
        ),
        forwarded_for=http_request.headers.get("x-forwarded-for"),
    )
    await enforce_signup_rate_limit(client_ip=client_ip)
    plan_name = payload.plan.lower().strip()
    if plan_name not in PLAN_BUDGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan. Use one of: {', '.join(PLAN_BUDGETS)}.",
        )

    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    try:
        password_hash = hash_password(payload.password)
    except WeakPasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = Store(
        name=payload.store_name,
        website_url=payload.website_url,
        plan=plan_name,
        monthly_budget=PLAN_BUDGETS[plan_name],
    )
    db.add(store)
    db.flush()  # assign store.id without committing yet

    user = User(
        store_id=store.id,
        email=payload.email.lower(),
        password_hash=password_hash,
    )
    db.add(user)

    raw_key, prefix, key_hash = generate_api_key()
    api_key = APIKey(store_id=store.id, key_prefix=prefix, key_hash=key_hash, name="Default Key")
    db.add(api_key)

    db.commit()
    db.refresh(user)
    db.refresh(store)

    token = create_access_token(user_id=user.id, store_id=store.id)

    return AuthResponse(
        access_token=token,
        user=_user_dict(user),
        store=_store_dict(store),
        api_key=raw_key,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    # Deliberately identical error message + roughly-constant work for
    # "no such user" and "wrong password" so a login attempt can't be
    # used to enumerate registered emails.
    generic_error = HTTPException(status_code=401, detail="Invalid email or password")

    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        # Still run a bcrypt check against a dummy hash so response
        # timing doesn't reveal whether the email exists.
        verify_password(payload.password, "$2b$12$" + "0" * 53)
        raise generic_error

    if not verify_password(payload.password, user.password_hash):
        raise generic_error

    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise generic_error

    from datetime import datetime

    user.last_login_at = datetime.utcnow()
    db.add(user)
    db.commit()

    token = create_access_token(user_id=user.id, store_id=store.id)
    return AuthResponse(access_token=token, user=_user_dict(user), store=_store_dict(store))


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == user.store_id).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"user": _user_dict(user), "store": _store_dict(store)}
