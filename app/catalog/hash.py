import hashlib
import json


def product_hash(
    product: dict,
) -> str:

    relevant = {
        "name": product.get("name"),
        "description":
            product.get("description"),
        "price":
            product.get("price"),
        "compare_at_price":
            product.get("compare_at_price"),
        "stock_quantity":
            product.get("stock_quantity"),
        "image_url":
            product.get("image_url"),
        "category":
            product.get("category"),
        "brand":
            product.get("brand"),
        "product_url":
            product.get("product_url"),
    }

    payload = json.dumps(
        relevant,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
