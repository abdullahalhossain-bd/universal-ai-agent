from abc import ABC, abstractmethod


class BaseTool(ABC):

    name: str = "base_tool"
    description: str = ""
    cost: float = 0.0

    @abstractmethod
    async def execute(
        self,
        tenant_id: str,
        **kwargs,
    ):
        raise NotImplementedError
