from datetime import datetime
from pydantic import BaseModel


class SyncJob(BaseModel):

    tenant_id: str

    datasource_id: str

    job_type: str = "product_sync"

    created_at: datetime | None = None
