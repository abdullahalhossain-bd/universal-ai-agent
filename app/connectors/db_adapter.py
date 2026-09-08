from abc import ABC, abstractmethod


class DatabaseAdapter(ABC):

    @abstractmethod
    async def get_tables(self):
        raise NotImplementedError

    @abstractmethod
    async def get_columns(self, table):
        raise NotImplementedError

    @abstractmethod
    async def sample_rows(self, table, limit=10):
        raise NotImplementedError
