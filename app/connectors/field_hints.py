"""Canonical ecommerce field vocabulary and source-column aliases.

This module is the single source of truth for datasource field mapping.
Keep canonical keys aligned with ``app.products.fields`` so every mapping
path produces a mapping that the product layer can consume.
"""

FIELD_HINTS = {
    "id": {
        "id", "product_id", "item_id", "external_id", "external_product_id",
        "uid", "uuid", "product_uuid", "item_ref", "unique_id", "product_code",
    },
    "name": {
        "name", "product_name", "item_name", "title", "product_title",
        "item_title", "product", "productname", "itemname", "nm",
    },
    "sku": {
        "sku", "product_sku", "item_sku", "stock_keeping_unit", "sku_code",
        "item_code", "variant_sku",
    },
    "barcode": {
        "barcode", "bar_code", "ean", "ean13", "ean_13", "upc", "gtin", "gtin13", "isbn",
    },
    "price": {
        "price", "selling_price", "sale_price", "current_price", "selling_amount",
        "amount", "cost", "sell_amt", "regular_price", "unit_price", "final_price",
    },
    "compare_at_price": {
        "compare_at_price", "original_price", "regular_price", "list_price",
        "mrp", "msrp", "was_price", "old_price",
    },
    "currency": {
        "currency", "currency_code", "price_currency", "currency_symbol",
    },
    "stock": {
        "stock", "stock_quantity", "quantity", "qty", "inventory", "available",
        "available_qty", "available_quantity", "qty_available", "inventory_quantity",
        "left", "qty_left", "left_qty", "stock_left", "remaining", "remaining_qty",
        "quantity_left", "quantity_remaining", "in_stock_qty", "stock_count",
        "product_left", "items_left",
    },
    "availability": {
        "availability", "available_status", "stock_status", "availability_status",
        "in_stock", "is_available", "is_in_stock",
    },
    "image": {
        "image", "image_url", "photo", "photo_url", "picture", "pic", "thumbnail",
        "featured_image", "main_image", "primary_image",
    },
    "images": {
        "images", "image_urls", "photos", "photo_urls", "gallery", "gallery_images",
    },
    "url": {
        "url", "product_url", "link", "product_link", "product_page", "permalink",
        "handle", "slug_url",
    },
    "description": {
        "description", "details", "product_description", "short_description",
        "long_description", "summary", "product_details",
    },
    "brand": {
        "brand", "brand_name", "manufacturer", "maker", "vendor_brand",
    },
    "category": {
        "category", "category_name", "product_category", "product_type", "type",
        "catag", "catagory", "product_catag", "cat",
    },
    "subcategory": {
        "subcategory", "sub_category", "sub_category_name", "category_level_2",
    },
    "tags": {
        "tags", "tag", "keywords", "product_tags", "labels",
    },
    "color": {
        "color", "colour", "color_name", "colour_name", "variant_color",
    },
    "size": {
        "size", "size_name", "variant_size", "dimension_size",
    },
    "material": {
        "material", "fabric", "composition", "material_type",
    },
    "variant": {
        "variant", "variant_name", "variant_title", "option", "options",
    },
    "weight": {
        "weight", "product_weight", "item_weight", "weight_value",
    },
    "rating": {
        "rating", "average_rating", "review_rating", "stars", "avg_rating",
    },
    "review_count": {
        "review_count", "reviews_count", "rating_count", "ratings_count", "num_reviews",
    },
    "discount": {
        "discount", "discount_percent", "discount_percentage", "sale_discount",
    },
    "created_at": {
        "created_at", "created", "date_created", "created_on", "published_at",
    },
    "updated_at": {
        "updated_at", "updated", "date_updated", "modified_at", "updated_on",
    },
}

# Backward-compatible alias used by older connector code.
FIELD_NAME_HINTS = FIELD_HINTS