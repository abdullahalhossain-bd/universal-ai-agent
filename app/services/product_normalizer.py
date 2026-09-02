from app.domain.product import Product


def normalize_product(
    raw: dict,
    mapping: dict,
) -> Product:

    return Product(

        id=str(raw[mapping["id"]]),

        name=str(raw[mapping["name"]]),

        price=(
            float(raw[mapping["price"]])
            if mapping.get("price")
            and raw.get(mapping["price"]) is not None
            else None
        ),

        stock=(
            float(raw[mapping["stock"]])
            if mapping.get("stock")
            and raw.get(mapping["stock"]) is not None
            else None
        ),

        image_url=(
            str(raw[mapping["image_url"]])
            if mapping.get("image_url")
            and raw.get(mapping["image_url"])
            else None
        ),
    )
