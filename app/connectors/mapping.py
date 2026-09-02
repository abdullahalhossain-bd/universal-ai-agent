FIELD_ALIASES = {

    "id": [
        "id",
        "product_id",
        "item_id",
        "uuid",
        "product_uuid",
    ],

    "name": [
        "name",
        "title",
        "product_name",
        "item_name",
    ],

    "price": [
        "price",
        "sale_price",
        "selling_price",
        "regular_price",
    ],

    "stock_quantity": [
        "stock",
        "qty",
        "quantity",
        "inventory",
        "stock_quantity",
    ],

    "image_url": [
        "image",
        "image_url",
        "thumbnail",
        "photo",
        "picture",
    ],

    "description": [
        "description",
        "details",
        "product_description",
        "short_description",
    ],

    "sku": [
        "sku",
        "product_code",
        "item_code",
    ],

    "brand": [
        "brand",
        "brand_name",
    ],

    "category": [
        "category",
        "category_name",
        "product_category",
    ],
}


def normalize(text: str):

    return (
        text.lower()
        .strip()
        .replace("-", "_")
        .replace(" ", "_")
    )


def map_fields(columns):

    normalized = {
        normalize(c): c
        for c in columns
    }

    mapping = {}

    for target, aliases in FIELD_ALIASES.items():

        for alias in aliases:

            alias = normalize(alias)

            if alias in normalized:

                mapping[target] = (
                    normalized[alias]
                )

                break

    return mapping
