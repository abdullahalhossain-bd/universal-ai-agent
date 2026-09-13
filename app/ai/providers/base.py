from abc import ABC, abstractmethod


class LLMProvider(ABC):

    @abstractmethod
    async def generate(
        self,
        messages,
        max_tokens=500,
    ):
        raise NotImplementedError
