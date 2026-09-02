from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
)

from sqlalchemy.orm import Session

from app.auth.dependency import (
    authenticate_api_key,
)

from app.auth.models import APIKey

from app.db.database import get_db

from app.db.models import Store

from app.core.security import (
    resolve_client_ip,
)

from app.core.rate_limit import (
    enforce_rate_limit,
)

from app.chat.schemas import (
    ChatRequest,
    ChatResponse,
)

from app.chat.service import (
    ChatService,
)


router = APIRouter(
    prefix="/v1/chat",
    tags=["Chat"],
)


@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    http_request: Request,
    response: Response,

    request: ChatRequest,

    api_key: APIKey = Depends(
        authenticate_api_key
    ),

    db: Session = Depends(
        get_db
    ),
):

    # ---------------------------------
    # Resolve authenticated store
    # ---------------------------------

    store = (
        db.query(Store)
        .filter(
            Store.id == api_key.store_id
        )
        .first()
    )

    if store is None:

        raise HTTPException(
            status_code=401,
            detail="Store not found",
        )

    if store.status == "suspended":
        raise HTTPException(
            status_code=403,
            detail="This store has been suspended. Contact support.",
        )

    # ---------------------------------
    # Resolve client IP
    # ---------------------------------

    # Anti-spoofing: X-Forwarded-For is only honored when
    # the direct peer is a configured trusted proxy. See
    # `resolve_client_ip` for the exact rules.
    client_ip = resolve_client_ip(
        peer_host=(
            http_request.client.host
            if http_request.client
            else None
        ),
        forwarded_for=(
            http_request.headers.get("x-forwarded-for")
        ),
    )

    # ---------------------------------
    # Redis dual rate limiting
    # ---------------------------------

    rate_limit = await enforce_rate_limit(
        store_id=store.id,
        plan=store.plan,
        client_ip=client_ip,
    )

    # ---------------------------------
    # Successful response rate-limit headers
    # ---------------------------------

    ip_limit = rate_limit["ip"]

    response.headers[
        "X-RateLimit-Limit"
    ] = str(
        ip_limit["limit"]
    )

    response.headers[
        "X-RateLimit-Remaining"
    ] = str(
        ip_limit["remaining"]
    )

    response.headers[
        "X-RateLimit-Reset"
    ] = str(
        ip_limit["reset"]
    )

    # ---------------------------------
    # Chat service
    # ---------------------------------

    service = ChatService(
        db=db
    )

    return await service.handle(
        store_id=store.id,
        request=request,
    )