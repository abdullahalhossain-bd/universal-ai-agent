"""
Unified context builder for the AI orchestration layer.

The ContextBuilder assembles a `UnifiedContext` from the user query plus
optional product / knowledge / conversation history. Downstream LLM
prompts consume this context to generate a final response.
"""

from dataclasses import dataclass, field


@dataclass
class UnifiedContext:
    """
    Result of `ContextBuilder.build(...)`.

    `query` is the raw user query.
    `items` is a list of context items (each a dict with `type` + `content`)
    that the LLM should consider when answering.
    """

    query: str
    items: list[dict] = field(default_factory=list)


class ContextBuilder:
    """
    Builds a `UnifiedContext` from the user query, retrieved products,
    retrieved knowledge chunks, and (optional) prior conversation history.
    """

    def build(
        self,
        query: str = "",
        products=None,
        knowledge=None,
        conversation=None,
    ) -> UnifiedContext:
        items: list[dict] = []

        for product in products or []:
            # `stock_quantity` is the legacy attribute name; fall back to
            # `stock` (the canonical attribute used by `app.db.models.Product`)
            # if the legacy field is missing.
            stock_value = getattr(
                product,
                "stock_quantity",
                None,
            )

            if stock_value is None:
                stock_value = getattr(
                    product,
                    "stock",
                    None,
                )

            items.append(
                {
                    "type": "product",
                    "content": (
                        f"Name: {getattr(product, 'name', '')}\n"
                        f"Price: {getattr(product, 'price', '')}\n"
                        f"Stock: {stock_value}\n"
                        f"Category: {getattr(product, 'category', '')}\n"
                        f"Brand: {getattr(product, 'brand', '')}"
                    ),
                }
            )

        for item in knowledge or []:
            content = getattr(
                item,
                "content",
                None,
            )

            if content is None and isinstance(item, dict):
                content = item.get("content", "")

            items.append(
                {
                    "type": "knowledge",
                    "content": content,
                }
            )

        for turn in conversation or []:
            items.append(
                {
                    "type": "conversation",
                    "content": turn,
                }
            )

        return UnifiedContext(
            query=query,
            items=items,
        )
