from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Store, APIKey
from app.db.agent_config import AgentConfig
from app.core.security import generate_api_key, resolve_client_ip
from app.core.rate_limit import enforce_signup_rate_limit
from app.core.tenant import get_current_store
from app.billing.plans import PLAN_BUDGETS

router = APIRouter(prefix="/v1/stores", tags=["stores"])

class CreateStoreRequest(BaseModel):
    name: str
    website_url: str | None = None
    plan: str = "starter"

@router.post("")
async def create_store(http_request: Request, payload: CreateStoreRequest, db: Session = Depends(get_db)):
    client_ip = resolve_client_ip(peer_host=http_request.client.host if http_request.client else None, forwarded_for=http_request.headers.get("x-forwarded-for"))
    await enforce_signup_rate_limit(client_ip=client_ip)
    plan_name = payload.plan.lower().strip()
    if plan_name not in PLAN_BUDGETS:
        raise HTTPException(status_code=400, detail="Invalid plan. Use starter, growth, or pro.")
    store = Store(name=payload.name, website_url=payload.website_url, plan=plan_name, monthly_budget=PLAN_BUDGETS[plan_name])
    db.add(store)
    db.flush()
    raw_key, prefix, key_hash = generate_api_key()
    db.add(APIKey(store_id=store.id, key_prefix=prefix, key_hash=key_hash))
    db.commit()
    return {"store_id": store.id, "name": store.name, "website_url": store.website_url, "plan": store.plan, "monthly_budget": float(store.monthly_budget), "status": store.status, "api_key": raw_key}

@router.get("/me")
def get_my_store(store: Store = Depends(get_current_store)):
    return {"store_id": store.id, "name": store.name, "website_url": store.website_url, "plan": store.plan, "monthly_budget": float(store.monthly_budget), "status": store.status}

class AgentConfigRequest(BaseModel):
    agent_name: str = Field(default="Shop Assistant", min_length=1, max_length=100)
    welcome_message: str = Field(default="Hi! How can I help you today?", min_length=1, max_length=1000)
    language: str = Field(default="auto", pattern="^(auto|en|bn)$")
    tone: str = Field(default="friendly", pattern="^(friendly|professional|concise|warm)$")
    system_instructions: str = Field(default="", max_length=5000)
    product_behavior: str = Field(default="accurate", pattern="^(accurate|helpful|sales)$")
    fallback_message: str = Field(default="I couldn't find that information. Please contact the store for help.", min_length=1, max_length=1000)
    enabled: bool = True
    auto_reply_enabled: bool = True

def _agent_config_response(config: AgentConfig):
    return {"agent_name": config.agent_name, "welcome_message": config.welcome_message, "language": config.language, "tone": config.tone, "system_instructions": config.system_instructions, "product_behavior": config.product_behavior, "fallback_message": config.fallback_message, "enabled": config.enabled, "auto_reply_enabled": config.auto_reply_enabled, "updated_at": config.updated_at}

def _get_or_create_agent_config(store: Store, db: Session):
    config = db.query(AgentConfig).filter(AgentConfig.store_id == store.id).first()
    if config is None:
        config = AgentConfig(id=__import__("uuid").uuid4().hex, store_id=store.id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

@router.get("/me/agent-config")
def get_agent_config(store: Store = Depends(get_current_store), db: Session = Depends(get_db)):
    return _agent_config_response(_get_or_create_agent_config(store, db))

@router.put("/me/agent-config")
def update_agent_config(payload: AgentConfigRequest, store: Store = Depends(get_current_store), db: Session = Depends(get_db)):
    config = _get_or_create_agent_config(store, db)
    for field in payload.model_fields:
        setattr(config, field, getattr(payload, field))
    db.commit()
    db.refresh(config)
    return _agent_config_response(config)
