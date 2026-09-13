from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.api_key import get_api_key
from app.commerce.models import CommerceActionRequest, CommerceActionResponse
from app.commerce.service import CommerceActionService
from app.db.database import get_db
from app.db.models import APIKey

router = APIRouter(prefix="/v1/actions", tags=["Commerce Actions"])


@router.post("", response_model=CommerceActionResponse)
async def execute_commerce_action(
    payload: CommerceActionRequest,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """Execute a validated commerce action for the authenticated store.

    The API key establishes the tenant. A client cannot supply another
    store_id, and local product reads are always scoped by that tenant.
    """
    service = CommerceActionService(db=db)
    return await service.execute(store_id=api_key.store_id, request=payload)
