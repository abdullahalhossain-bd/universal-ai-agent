from fastapi import APIRouter
from pydantic import BaseModel

from app.connectors.config import ConnectorConfig
from app.connectors.factory import ConnectorFactory


router = APIRouter(
    prefix="/connectors",
    tags=["Connectors"],
)


class ConnectionTestRequest(BaseModel):
    config: ConnectorConfig


@router.post("/test")
async def test_connector(
    payload: ConnectionTestRequest,
):

    connector = ConnectorFactory.create(
        payload.config
    )

    connected = await connector.test_connection()

    return {
        "connected": connected,
        "connector_type": (
            payload.config.connector_type
        ),
    }
