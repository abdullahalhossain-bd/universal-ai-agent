from types import SimpleNamespace

from app.chat.context import (
    ChatContext,
)


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