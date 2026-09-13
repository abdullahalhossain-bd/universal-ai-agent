from datetime import datetime
from pydantic import BaseModel


class ImageRecord(BaseModel):

    image_id: str
    tenant_id: str
    user_id: str | None = None
    conversation_id: str | None = None
    storage_key: str
    mime_type: str
    size: int
    image_hash: str | None = None
    created_at: datetime | None = None
