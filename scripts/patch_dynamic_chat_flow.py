from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "app/chat/service.py"
CI = ROOT / ".github/workflows/ci.yml"

text = SERVICE.read_text(encoding="utf-8-sig")

text = text.replace(
    "from app.db.models import Product, QueryEvent\n",
    "from app.db.models import Product, QueryEvent\nfrom app.products.attribute_filters import apply_attribute_filters\n",
    1,
)

# Persist dynamic attributes in product context so pagination restores them.
old = '''                filter_data = {\n                    "min_price": filters.min_price,\n                    "max_price": filters.max_price,\n                    "in_stock": filters.in_stock,\n                    "product_name": filters.product_name,\n                }'''
new = '''                filter_data = {\n                    "min_price": filters.min_price,\n                    "max_price": filters.max_price,\n                    "in_stock": filters.in_stock,\n                    "product_name": filters.product_name,\n                    "attributes": getattr(filters, "attributes", {}) or {},\n                }'''
assert old in text
text = text.replace(old, new, 1)

# Apply structured attribute predicates to the primary search, independently
# of legacy name/description/category text matching.
old = '''            if filters.in_stock:\n\n                # NULL stock means the merchant hasn't set up\n                # inventory tracking for this product yet — treat\n                # that as "unknown", not "out of stock". Only an\n                # explicit stock of 0 should hide the product from\n                # an in-stock-filtered search (e.g. "laptop ase").\n                query = query.filter(\n                    or_(\n                        Product.stock.is_(None),\n                        Product.stock > 0,\n                    )\n                )\n\n        # Planner-cleaned search text'''
new = '''            if filters.in_stock:\n\n                # NULL stock means the merchant hasn't set up\n                # inventory tracking for this product yet — treat\n                # that as "unknown", not "out of stock". Only an\n                # explicit stock of 0 should hide the product from\n                # an in-stock-filtered search (e.g. "laptop ase").\n                query = query.filter(\n                    or_(\n                        Product.stock.is_(None),\n                        Product.stock > 0,\n                    )\n                )\n\n            query = apply_attribute_filters(\n                query,\n                getattr(filters, "attributes", {}) or {},\n                Product.attributes,\n            )\n\n        # Planner-cleaned search text'''
assert old in text
text = text.replace(old, new, 1)

# Apply attributes to the learned-term retry.
old = '''                    if filters.in_stock:\n                        retry_query = retry_query.filter(\n                            or_(\n                                Product.stock.is_(None),\n                                Product.stock > 0,\n                            )\n                        )\n\n                results = ('''
new = '''                    if filters.in_stock:\n                        retry_query = retry_query.filter(\n                            or_(\n                                Product.stock.is_(None),\n                                Product.stock > 0,\n                            )\n                        )\n\n                    retry_query = apply_attribute_filters(\n                        retry_query,\n                        getattr(filters, "attributes", {}) or {},\n                        Product.attributes,\n                    )\n\n                results = ('''
assert old in text
text = text.replace(old, new, 1)

# Apply attributes to the last-resort correction retry.
old = '''                        if filters.in_stock:\n                            retry_query = retry_query.filter(\n                                or_(\n                                    Product.stock.is_(None),\n                                    Product.stock > 0,\n                                )\n                            )\n\n                    results = ('''
new = '''                        if filters.in_stock:\n                            retry_query = retry_query.filter(\n                                or_(\n                                    Product.stock.is_(None),\n                                    Product.stock > 0,\n                                )\n                            )\n\n                        retry_query = apply_attribute_filters(\n                            retry_query,\n                            getattr(filters, "attributes", {}) or {},\n                            Product.attributes,\n                        )\n\n                    results = ('''
assert old in text
text = text.replace(old, new, 1)

# Pagination: restore attributes from the saved context.
old = '''        in_stock = filters_data.get(\n            "in_stock",\n            False,\n        )\n\n        if min_price is not None:'''
new = '''        in_stock = filters_data.get(\n            "in_stock",\n            False,\n        )\n\n        attributes = filters_data.get("attributes") or {}\n        if not isinstance(attributes, dict):\n            attributes = {}\n\n        if min_price is not None:'''
assert old in text
text = text.replace(old, new, 1)

old = '''        if in_stock:\n\n            query = query.filter(\n                Product.stock > 0\n            )\n\n        # -----------------------------\n        # Restore search terms'''
new = '''        if in_stock:\n\n            query = query.filter(\n                or_(\n                    Product.stock.is_(None),\n                    Product.stock > 0,\n                )\n            )\n\n        query = apply_attribute_filters(\n            query,\n            attributes,\n            Product.attributes,\n        )\n\n        # -----------------------------\n        # Restore search terms'''
assert old in text
text = text.replace(old, new, 1)

# Pagination's legacy text terms must not reintroduce extracted attribute
# values as mandatory name/description terms. Use the stored product_name
# produced by the planner; for attribute-only searches it is empty.
SERVICE.write_text(text, encoding="utf-8")

# Remove this one-shot patch step after it has executed, so subsequent CI
# runs are normal. The markers are intentionally unique.
ci = CI.read_text(encoding="utf-8")
start = ci.find("\n      # BEGIN ONE_SHOT_DYNAMIC_CHAT_PATCH\n")
end = ci.find("\n      # END ONE_SHOT_DYNAMIC_CHAT_PATCH\n", start)
if start != -1 and end != -1:
    ci = ci[:start] + ci[end + len("\n      # END ONE_SHOT_DYNAMIC_CHAT_PATCH\n"):]
    CI.write_text(ci, encoding="utf-8")
