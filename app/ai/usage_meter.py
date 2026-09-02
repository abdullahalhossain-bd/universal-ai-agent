from datetime import datetime
from pydantic import BaseModel


class UsageRecord(BaseModel):

    tenant_id: str
    request_id: str
    route: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    created_at: datetime | None = None
