from app.connectors.base.connector import Connector


class ConnectorRegistry:

    def __init__(self):
        self._connectors: dict[
            str,
            type[Connector],
        ] = {}

    def register(
        self,
        name: str,
        connector: type[Connector],
    ) -> None:

        self._connectors[name] = connector

    def get(
        self,
        name: str,
    ) -> type[Connector]:

        if name not in self._connectors:
            raise ValueError(
                f"Unknown connector: {name}"
            )

        return self._connectors[name]

    def available(self) -> list[str]:
        return list(self._connectors.keys())
