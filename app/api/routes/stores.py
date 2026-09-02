from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.database import get_db

from app.db.models import (
    Store,
    APIKey,
)

from app.core.security import (
    generate_api_key,
    resolve_client_ip,
)

from app.core.rate_limit import (
    enforce_signup_rate_limit,
)

from app.core.tenant import (
    get_current_store,
)

from app.billing.plans import PLAN_BUDGETS


router = APIRouter(
    prefix="/v1/stores",
    tags=["stores"],
)


# ---------------------------------
# Create Store
# ---------------------------------

class CreateStoreRequest(BaseModel):

    name: str

    website_url: str | None = None

    plan: str = "starter"


@router.post("")
async def create_store(
    http_request: Request,
    payload: CreateStoreRequest,
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

    # Public onboarding remains supported, but tenant and API-key
    # creation is bounded per source IP and fails closed without Redis.
    # Dashboard signup applies the same control in app.api.routes.auth.
    # The response exposes the raw key only for this one creation call.
    # The limiter result is intentionally not returned to avoid coupling
    # this bootstrap response to rate-limit headers.
    await enforce_signup_rate_limit(client_ip=client_ip)

    plan_name = payload.plan.lower().strip()

    if plan_name not in PLAN_BUDGETS:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid plan. "
                "Use starter, growth, or pro."
            ),
        )

    store = Store(
        name=payload.name,
        website_url=payload.website_url,
        plan=plan_name,
        monthly_budget=PLAN_BUDGETS[
            plan_name
        ],
    )

    db.add(store)

    db.flush()

    raw_key, prefix, key_hash = (
        generate_api_key()
    )

    api_key = APIKey(
        store_id=store.id,
        key_prefix=prefix,
        key_hash=key_hash,
    )

    db.add(api_key)

    db.commit()

    return {
        "store_id": store.id,
        "name": store.name,
        "website_url": store.website_url,
        "plan": store.plan,
        "monthly_budget": float(
            store.monthly_budget
        ),
        "status": store.status,
        "api_key": raw_key,
    }


# ---------------------------------
# Current Store
# ---------------------------------

@router.get("/me")
def get_my_store(
    store: Store = Depends(
        get_current_store
    ),
):

    return {
        "store_id": store.id,
        "name": store.name,
        "website_url": store.website_url,
        "plan": store.plan,
        "monthly_budget": float(
            store.monthly_budget
        ),
        "status": store.status,
    }