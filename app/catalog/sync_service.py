"""LEGACY — superseded by app.sync.service.ProductSyncService.
Uses tenant_id + repository abstraction that is not part of the
store-scoped products architecture. Do not use for new work.
"""

from app.catalog.hash import (
    product_hash,
)


class ProductSyncService:

    def __init__(
        self,
        repository,
    ):

        self.repository = repository

    async def sync_product(
        self,
        tenant_id: str,
        product: dict,
    ):

        new_hash = product_hash(
            product
        )

        existing = await (
            self.repository
            .find_by_external_id(
                tenant_id,
                product["external_id"],
            )
        )

        if existing:

            if (
                existing.content_hash
                == new_hash
            ):

                return {
                    "status": "unchanged"
                }

            await self.repository.update(
                existing.id,
                {
                    **product,
                    "content_hash":
                        new_hash,
                },
            )

            return {
                "status": "updated",
                "product_id":
                    existing.id,
            }

        created = await (
            self.repository.create(
                tenant_id=tenant_id,
                data={
                    **product,
                    "content_hash":
                        new_hash,
                },
            )
        )

        return {
            "status": "created",
            "product_id": created.id,
        }
