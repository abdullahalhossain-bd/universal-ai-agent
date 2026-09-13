from abc import ABC, abstractmethod


class SearchProvider(ABC):

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
    ):
        raise NotImplementedError
