from abc import ABC, abstractmethod


class LLMPlanner(ABC):

    @abstractmethod
    async def plan(
        self,
        query: str,
    ):
        raise NotImplementedError
