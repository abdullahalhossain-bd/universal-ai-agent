from fastapi import (
    Depends,
    HTTPException,
)
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.security import hash_api_key
from app.db.database import get_db
from app.db.models import APIKey


api_key_header = APIKeyHeader(
    name="x-api-key",
    auto_error=False,
)


async def get_api_key(
    x_api_key: str | None = Depends(
        api_key_header
    ),
    db: Session = Depends(get_db),
) -> APIKey:

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required",
        )

    if not x_api_key.startswith("pk_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    key_hash = hash_api_key(
        x_api_key
    )

    api_key = (
        db.query(APIKey)
        .filter(
            APIKey.key_hash == key_hash,
            APIKey.revoked_at.is_(None),
        )
        .first()
    )

    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
        )

    return api_key