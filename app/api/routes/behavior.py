from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import Product, Store
from app.search.behavior_learning import record_event, ALLOWED_EVENTS

router = APIRouter(prefix="/v1/behavior", tags=["Behavior Learning"])


class BehaviorEventRequest(BaseModel):
    interaction_id: str = Field(min_length=1, max_length=36)
    event_type: str = Field(min_length=1, max_length=40)
    product_id: str | None = Field(default=None, max_length=100)
    conversation_id: str | None = Field(default=None, max_length=200)
    query: str | None = Field(default=None, max_length=500)
    value: float | None = Field(default=None, ge=0, le=1000000)
    metadata: dict = Field(default_factory=dict)


@router.post("/events")
def create_behavior_event(
    request: BehaviorEventRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    if request.event_type not in ALLOWED_EVENTS:
        raise HTTPException(status_code=400, detail="Unsupported behavior event type.")

    if request.product_id:
        exists = (
            db.query(Product.id)
            .filter(Product.store_id == store.id, Product.id == request.product_id)
            .first()
        )
        if exists is None:
            raise HTTPException(status_code=404, detail="Product not found for this store.")

    try:
        event = record_event(
            db,
            store_id=store.id,
            interaction_id=request.interaction_id,
            event_type=request.event_type,
            product_id=request.product_id,
            conversation_id=request.conversation_id,
            query=request.query,
            value=request.value,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "event_id": event.id}
