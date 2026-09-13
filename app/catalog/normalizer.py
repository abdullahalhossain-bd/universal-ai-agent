from app.catalog.schema import (
    UniversalProduct,
)


def normalize_product(
    product: UniversalProduct,
) -> dict:

    return {
        "external_id": product.external_id,
        "sku": product.sku,
        "name": product.name.strip(),
        "description": product.description,
        "price": product.price,
        "compare_at_price":
            product.compare_at_price,
        "currency": product.currency,
        "stock_quantity":
            product.stock_quantity,
        "in_stock":
            product.in_stock,
        "category": product.category,
        "brand": product.brand,
        "image_url": product.image_url,
        "product_url": product.product_url,
        "metadata_json":
            product.metadata,
    }
