from abc import ABC, abstractmethod


class DataConnector(ABC):

    @abstractmethod
    async def test_connection(self):
        raise NotImplementedError

    @abstractmethod
    async def discover_schema(self):
        raise NotImplementedError

    @abstractmethod
    async def fetch_products(self):
        raise NotImplementedError

    @abstractmethod
    async def fetch_product(self, product_id):
        raise NotImplementedError
