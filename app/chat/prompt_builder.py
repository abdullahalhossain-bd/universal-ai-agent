class PromptBuilder:

    def build(
        self,
        context,
    ):

        product_text = "\n".join(
            self._product_text(p)
            for p in context.products
        )

        knowledge_text = "\n".join(
            self._knowledge_text(k)
            for k in context.knowledge
        )

        history_text = "\n".join(
            f"{item['role']}: "
            f"{item['content']}"
            for item in context.history
        )

        return [
            {
                "role": "system",
                "content": (
                    "You are an ecommerce "
                    "customer assistant. "
                    "Answer only using "
                    "provided context. "
                    "Never invent product "
                    "price, stock, policy "
                    "or delivery information."
                ),
            },
            {
                "role": "system",
                "content": (
                    f"PRODUCTS:\n"
                    f"{product_text}\n\n"
                    f"WEBSITE KNOWLEDGE:\n"
                    f"{knowledge_text}"
                ),
            },
            {
                "role": "system",
                "content": (
                    f"RECENT HISTORY:\n"
                    f"{history_text}"
                ),
            },
            {
                "role": "user",
                "content": context.user_message,
            },
        ]

    def _product_text(self, product):

        return str(
            product.metadata
        )

    def _knowledge_text(self, item):

        return item.content
