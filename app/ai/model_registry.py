from pydantic import BaseModel


class ModelConfig(BaseModel):

    model: str
    provider: str
    input_cost: float
    output_cost: float
    max_tokens: int
    enabled: bool = True
    priority: int = 0


# Actual pricing values should be loaded from DB/config at deploy time,
# not hardcoded here. This is a placeholder structure only.
MODEL_REGISTRY: dict[str, ModelConfig] = {}
