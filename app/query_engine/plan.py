from pydantic import BaseModel


class PlanStep(BaseModel):

    tool: str
    filters: dict = {}
    query: str | None = None
    depends_on: list[str] = []


class QueryPlan(BaseModel):

    version: str = "1"
    intent: str
    steps: list[PlanStep] = []
