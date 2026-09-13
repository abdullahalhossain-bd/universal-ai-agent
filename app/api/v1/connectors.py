from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.config import ConnectorConfig
from app.connectors.factory import ConnectorFactory
from app.core.network_guard import assert_safe_connection_host
from app.core.tenant import get_current_store
from app.db.database import get_db
from app.db.models import Store

router = APIRouter(
    prefix="/connectors",
    tags=["Connectors"],
)


class ConnectionTestRequest(BaseModel):
    config: ConnectorConfig


@router.post("/test")
async def test_connector(
    payload: ConnectionTestRequest,
    store: Store = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    """Probe a merchant-supplied connector configuration.

    This route is authenticated (merchant JWT/API key) and SSRF-guarded:
    the supplied connection URL is resolved and private/internal/loopback
    targets are rejected BEFORE any connection attempt, so it can never be
    used as an unauthenticated internal-network scanner.
    """
    config = payload.config
    try:
        if config.connection_url:
            assert_safe_connection_host(config.connection_url)
        if config.api_base_url:
            assert_safe_connection_host(config.api_base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        connector = ConnectorFactory.create(config)
        connected = await connector.test_connection()
    except (ValueError, ConnectionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"connection test failed: {type(exc).__name__}") from exc

    return {
        "connected": connected,
        "connector_type": (
            config.connector_type
        ),
    }
