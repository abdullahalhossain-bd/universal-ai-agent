from abc import ABC, abstractmethod
from typing import Any

from app.discovery.models import DatabaseSchema
from app.schemas.product import UniversalProduct


class Connector(ABC):
    """
    Universal interface for accessing merchant data.

    Core application must depend on this interface,
    never directly on MySQL/PostgreSQL/etc.
    """

    @abstractmethod
    async def test_connection(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def discover(self) -> DatabaseSchema:
        raise NotImplementedError

    @abstractmethod
    async def get_products(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UniversalProduct]:
        raise NotImplementedError

    @abstractmethod
    async def get_product(
        self,
        product_id: str,
    ) -> UniversalProduct | None:
        raise NotImplementedError

    @abstractmethod
    async def get_inventory(
        self,
        product_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_store_info(
        self,
    ) -> dict[str, Any]:
        raise NotImplementedError
