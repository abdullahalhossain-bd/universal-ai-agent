from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Store
from app.core.tenant import get_current_store
from app.search.ranking import search_and_rank


router = APIRouter(
    prefix="/v1/products",
    tags=["products"],
)


@router.get("/search")
def search(
    q: str = Query(
        min_length=1,
        max_length=200,
    ),

    max_price: float | None = None,

    min_price: float | None = None,

    in_stock: bool | None = None,

    limit: int = Query(
        default=20,
        ge=1,
        le=50,
    ),

    db: Session = Depends(get_db),

    store: Store = Depends(
        get_current_store
    ),
):

    terms = q.split()

    products = search_and_rank(
        db=db,
        store_id=store.id,
        search_terms=terms,
        max_price=max_price,
        min_price=min_price,
        in_stock=in_stock,
        limit=limit,
    )

    return {
        "count": len(products),

        "items": [
            {
                "id": product.id,
                "name": product.name,
                "price": (
                    float(product.price)
                    if product.price is not None
                    else None
                ),
                "stock": (
                    float(product.stock)
                    if product.stock is not None
                    else None
                ),
                "image_url": product.image_url,
                "product_url": product.product_url,
            }

            for product in products
        ],
    }
