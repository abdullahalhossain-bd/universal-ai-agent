from app.discovery.models import (
    DatabaseSchema,
    TableRole,
)


ROLE_PATTERNS = {
    "product": [
        "product",
        "products",
        "item",
        "items",
        "catalog",
    ],
    "inventory": [
        "inventory",
        "stock",
        "stocks",
        "warehouse",
    ],
    "image": [
        "image",
        "images",
        "photo",
        "photos",
        "media",
    ],
    "category": [
        "category",
        "categories",
        "catalog_category",
    ],
    "brand": [
        "brand",
        "brands",
        "manufacturer",
    ],
    "order": [
        "order",
        "orders",
        "purchase",
    ],
    "customer": [
        "customer",
        "customers",
        "user",
        "users",
        "buyer",
    ],
}


class TableRoleAnalyzer:

    def analyze(
        self,
        schema: DatabaseSchema,
    ) -> list[TableRole]:

        results = []

        for table in schema.tables:

            table_name = table.name.lower()

            best_role = None
            best_score = 0.0
            evidence = []

            for role, patterns in ROLE_PATTERNS.items():

                for pattern in patterns:

                    if table_name == pattern:
                        score = 0.95
                    elif pattern in table_name:
                        score = 0.75
                    else:
                        continue

                    if score > best_score:
                        best_score = score
                        best_role = role
                        evidence = [
                            f"table-name-match:{pattern}"
                        ]

            if best_role:
                results.append(
                    TableRole(
                        table=table.name,
                        role=best_role,
                        confidence=best_score,
                        evidence=evidence,
                    )
                )

        return results
