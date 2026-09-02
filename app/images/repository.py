"""
Repository for `ChatImage` rows (see app.db.models.ChatImage).

Every lookup is store-scoped — `get()` always filters by
(store_id, id) so one merchant can never resolve another
merchant's `image_id` into image bytes/analysis, mirroring the
tenant-isolation pattern used by every other repository in this
codebase (see tests/test_tenant_isolation.py).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ChatImage


class ImageRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        store_id: str,
        storage_key: str,
        mime_type: str,
        size: int,
        image_hash: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
    ) -> ChatImage:

        record = ChatImage(
            store_id=store_id,
            storage_key=storage_key,
            mime_type=mime_type,
            size=size,
            image_hash=image_hash,
            conversation_id=conversation_id,
            user_id=user_id,
        )

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        return record

    def get(
        self,
        *,
        store_id: str,
        image_id: str,
    ) -> ChatImage | None:

        return (
            self.db.query(ChatImage)
            .filter(
                ChatImage.store_id == store_id,
                ChatImage.id == image_id,
            )
            .first()
        )
