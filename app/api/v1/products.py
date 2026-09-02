from fastapi import APIRouter

from app.core.config import settings
from app.services.query_engine import QueryEngine
from app.services.query_models import (
    ProductSearchRequest,
)


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


DEMO_MAPPING = {
    "id": "id",
    "name": "name",
    "description": "description",
    "price": "price",
    "stock": "stock",
    "image": "image_url",
}


@router.post("/search")
async def search_products(
    request: ProductSearchRequest,
):

    engine = QueryEngine(
        database_url=settings.database_url,
        mapping=DEMO_MAPPING,
        product_table="products",
    )

    products = engine.search_products(
        request
    )

    return {
        "count": len(products),
        "products": [
            product.model_dump(
                mode="json"
            )
            for product in products
        ],
    }
