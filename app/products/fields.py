# Canonical product fields supported by datasource mapping and raw catalog access.
#
# Merchant-specific attributes must NOT be added here. They belong under the
# `attributes` mapping namespace so a new merchant field never requires a
# platform code change.
ALLOWED_PRODUCT_FIELDS = {
    "id", "name", "sku", "barcode", "price", "compare_at_price", "currency",
    "stock", "availability", "image", "images", "url", "description", "brand",
    "category", "subcategory", "tags", "color", "size", "material", "variant",
    "weight", "rating", "review_count", "discount", "created_at", "updated_at",
}
