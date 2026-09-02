from pydantic import BaseModel


class ConversationState(BaseModel):

    last_products: list[dict] = []

    last_product_id: str | None = None

    last_intent: str | None = None

    last_query: str | None = None
