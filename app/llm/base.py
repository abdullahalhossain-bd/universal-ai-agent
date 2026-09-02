from abc import ABC, abstractmethod


class LLMProvider(ABC):

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        **kwargs,
    ) -> str:

        raise NotImplementedError
