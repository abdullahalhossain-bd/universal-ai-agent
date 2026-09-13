from types import SimpleNamespace

from app.chat.context import (
    ChatContext,
)
from app.search.recommendations import rank_products


class ContextBuilder:

    def build(
        self,
        tenant_id: str,
        session_id: str,
        message: str,
        history=None,
        products=None,
        knowledge=None,
    ):

        history = history or []
        products = products or []
        knowledge = knowledge or []

        # Recommendation queries should be grounded in the strongest
        # catalog evidence before the LLM sees the candidates. Mutating
        # the caller's list keeps the API product-card order aligned with
        # the recommendation order without adding another DB query.
        lowered = (message or "").casefold()
        recommendation_cues = (
            "best", "top", "recommend", "recommended", "suggest",
            "suggestion", "best seller", "best-seller",
            "সেরা", "সর্বোত্তম", "ভালো", "ভাল", "সাজেস্ট", "রিকমেন্ড",
            "সবচেয়ে ভালো", "সবচেয়ে ভালো",
        )
        if products and any(cue in lowered for cue in recommendation_cues):
            products[:] = rank_products(products)

        normalized_products = []

        for product in products:

            normalized_products.append(
                SimpleNamespace(
                    source_type="product",
                    title=getattr(
                        product,
                        "name",
                        None,
                    ),
                    content=(
                        f"Product: "
                        f"{getattr(product, 'name', '')}\n"
                        f"Price: "
                        f"{getattr(product, 'price', None)}\n"
                        f"Stock: "
                        f"{getattr(product, 'stock', None)}\n"
                        f"Rating: "
                        f"{getattr(product, 'rating', None)}\n"
                        f"Review count: "
                        f"{getattr(product, 'review_count', None)}\n"
                        f"Sales count: "
                        f"{getattr(product, 'sales_count', None)}\n"
                        f"Bestseller score: "
                        f"{getattr(product, 'bestseller_score', None)}\n"
                        f"Category: "
                        f"{getattr(product, 'category', None)}\n"
                        f"Description: "
                        f"{getattr(product, 'description', None)}\n"
                        f"Attributes: "
                        f"{getattr(product, 'attributes', None)}\n"
                        f"Image: "
                        f"{getattr(product, 'image_url', None)}\n"
                        f"URL: "
                        f"{getattr(product, 'product_url', None)}"
                    ),
                    url=getattr(
                        product,
                        "product_url",
                        None,
                    ),
                    product=product,
                )
            )

        normalized_knowledge = []

        for item in knowledge:

            if isinstance(
                item,
                dict,
            ):

                normalized_knowledge.append(
                    SimpleNamespace(
                        source_type="website",
                        title=item.get(
                            "title"
                        ),
                        content=item.get(
                            "content",
                            "",
                        ),
                        url=item.get(
                            "url"
                        ),
                    )
                )

            else:

                normalized_knowledge.append(
                    SimpleNamespace(
                        source_type="website",
                        title=getattr(
                            item,
                            "title",
                            None,
                        ),
                        content=getattr(
                            item,
                            "content",
                            "",
                        ),
                        url=getattr(
                            item,
                            "url",
                            None,
                        ),
                    )
                )

        return ChatContext(
            tenant_id=tenant_id,
            session_id=session_id,
            user_message=message,
            history=history,
            products=normalized_products,
            knowledge=normalized_knowledge,
        )