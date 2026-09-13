from pydantic import BaseModel, Field

from app.ai.actions import AllowedAction


class LLMAction(BaseModel):

    type: AllowedAction

    query: str | None = None

    filters: dict = Field(
        default_factory=dict
    )


class LLMQueryPlan(BaseModel):

    actions: list[LLMAction] = Field(
        min_length=1,
        max_length=5
    )
