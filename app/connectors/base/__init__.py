"""
Connectors base package.

Exposes two related but distinct abstractions:

1. ``BaseConnector``  — minimal async interface (test_connection, discover_schema,
   fetch_products, get_product, get_stock) used by the per-DB connector
   implementations such as ``MySQLConnector`` in ``app.connectors.mysql``.

2. ``Connector``       — richer universal interface (discover, get_products,
   get_product, get_inventory, get_store_info) used by the connector registry
   and REST/PostgreSQL connectors. See ``app.connectors.base.connector``.

Originally these lived in two places:
- ``app/connectors/base.py``        (BaseConnector)
- ``app/connectors/base/connector.py`` (Connector)

Python cannot have both a module file and a package directory with the same
name — the package wins, so ``from app.connectors.base import BaseConnector``
silently broke. We resolve this by re-exporting ``BaseConnector`` from the
package ``__init__.py`` and removing the conflicting module file.
"""
from abc import ABC, abstractmethod
from typing import Any

# Re-export Connector so ``from app.connectors.base import Connector`` works too.
from app.connectors.base.connector import Connector  # noqa: E402,F401


class BaseConnector(ABC):
    """Minimal async connector interface consumed by per-DB connectors."""

    @abstractmethod
    async def test_connection(self) -> bool:
        ...

    @abstractmethod
    async def discover_schema(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def fetch_products(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def get_product(
        self,
        product_id: str,
    ) -> dict[str, Any] | None:
        ...

    @abstractmethod
    async def get_stock(
        self,
        product_id: str,
    ) -> float | None:
        ...


__all__ = ["BaseConnector", "Connector"]
