"""
Connector factory.

Given a `ConnectorConfig` (or a legacy `(database_type, url)` pair), return
the right connector instance.
"""

from typing import overload

from app.connectors.config import ConnectorConfig
from app.connectors.mysql import MySQLConnector
from app.connectors.postgresql import PostgreSQLConnector
from app.connectors.rest import RESTConnector


class ConnectorFactory:
    """
    Factory for creating connectors from a `ConnectorConfig` or from a legacy
    `(database_type, url)` argument pair.
    """

    @overload
    @staticmethod
    def create(config: ConnectorConfig) -> object: ...

    @overload
    @staticmethod
    def create(database_type: str, url: str) -> object: ...

    @staticmethod
    def create(*args, **kwargs) -> object:
        """
        Accepted call forms:
            create(config: ConnectorConfig)
            create(database_type: str, url: str)
        """

        if (
            len(args) == 1
            and not kwargs
            and isinstance(args[0], ConnectorConfig)
        ):
            return ConnectorFactory._from_config(args[0])

        if (
            len(args) == 2
            and isinstance(args[0], str)
            and isinstance(args[1], str)
        ):
            return ConnectorFactory._from_type_and_url(
                args[0],
                args[1],
            )

        raise TypeError(
            "ConnectorFactory.create expects either "
            "(ConnectorConfig) or (database_type: str, url: str). "
            f"Got args={args!r} kwargs={kwargs!r}"
        )

    @staticmethod
    def _from_config(config: ConnectorConfig) -> object:
        connector_type = config.connector_type.lower()

        if connector_type == "postgresql":
            if not config.connection_url:
                raise ValueError(
                    "PostgreSQL connector requires `connection_url`."
                )
            return PostgreSQLConnector(config.connection_url)

        if connector_type == "mysql":
            if not config.connection_url:
                raise ValueError(
                    "MySQL connector requires `connection_url`."
                )
            from sqlalchemy.engine import make_url

            url = make_url(config.connection_url)
            return MySQLConnector(
                host=url.host or "localhost",
                port=url.port or 3306,
                username=url.username or "",
                password=url.password or "",
                database=url.database or "",
            )

        if connector_type == "rest":
            if not config.api_base_url:
                raise ValueError(
                    "REST connector requires `api_base_url`."
                )
            return RESTConnector(
                base_url=config.api_base_url,
                api_key=config.api_key,
                options=config.options,
            )

        raise ValueError(
            f"Unsupported connector type: {connector_type}"
        )

    @staticmethod
    def _from_type_and_url(
        database_type: str,
        url: str,
    ) -> object:
        normalized = database_type.lower()

        if normalized in {"postgres", "postgresql"}:
            return PostgreSQLConnector(url)

        if normalized == "mysql":
            from sqlalchemy.engine import make_url

            parsed = make_url(url)
            return MySQLConnector(
                host=parsed.host or "localhost",
                port=parsed.port or 3306,
                username=parsed.username or "",
                password=parsed.password or "",
                database=parsed.database or "",
            )

        if normalized == "rest":
            return RESTConnector(base_url=url)

        raise ValueError(
            f"Unsupported database type: {database_type}"
        )
