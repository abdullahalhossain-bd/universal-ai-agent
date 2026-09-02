from typing import Literal

from pydantic import BaseModel, Field


class ConnectorConfig(BaseModel):

    connector_type: Literal[
        "postgresql",
        "mysql",
        "rest",
    ]

    connection_url: str | None = None

    api_base_url: str | None = None

    api_key: str | None = None

    options: dict = Field(
        default_factory=dict
    )
