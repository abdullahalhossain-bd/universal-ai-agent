FIELD_ALIASES = {

    "external_id": {
        "id",
        "product_id",
        "product_uuid",
        "uuid",
    },

    "sku": {
        "sku",
        "product_code",
        "item_code",
    },

    "name": {
        "name",
        "title",
        "product_name",
        "product_title",
    },

    "price": {
        "price",
        "selling_price",
        "sale_price",
        "current_price",
        "selling",
    },

    "stock_quantity": {
        "stock",
        "quantity",
        "qty",
        "inventory",
        "available_quantity",
    },

    "image_url": {
        "image",
        "image_url",
        "thumbnail",
        "photo",
    },

    "description": {
        "description",
        "details",
        "product_description",
    },

    "category": {
        "category",
        "category_name",
        "product_category",
    },

    "brand": {
        "brand",
        "brand_name",
        "manufacturer",
    },
}


def classify_field(
    column_name: str,
):

    normalized = (
        column_name
        .strip()
        .lower()
    )

    for target, aliases in (
        FIELD_ALIASES.items()
    ):

        if normalized in aliases:

            return target

    return None
