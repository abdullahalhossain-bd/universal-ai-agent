from fastapi import (
    APIRouter,
    Depends,
)

from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.tenant import get_current_store

from app.query.parser import parse_query
from app.search.ranking import search_and_rank

from app.responses.composer import (
    compose_response,
)


router = APIRouter(
    prefix="/v1/chat",
    tags=["chat"],
)


@router.post("")
def chat(
    payload: dict,

    db: Session = Depends(get_db),

    store=Depends(
        get_current_store
    ),
):

    message = payload.get(
        "message",
        "",
    ).strip()

    if not message:

        return {
            "message": "Please enter a message.",
            "intent": "unknown",
            "products": [],
        }

    parsed = parse_query(
        message
    )

    if parsed.intent == "product_search":

        products = search_and_rank(
            db=db,
            store_id=store.id,
            search_terms=parsed.search_terms,
            max_price=(
                parsed.filters.max_price
            ),
            min_price=(
                parsed.filters.min_price
            ),
            in_stock=(
                parsed.filters.in_stock
            ),
        )

        return compose_response(
            intent=parsed.intent,
            products=products,
            max_price=(
                parsed.filters.max_price
            ),
        )

    return compose_response(
        intent=parsed.intent,
        products=[],
    )
