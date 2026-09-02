class TemplateResponder:

    def respond(
        self,
        context,
    ):

        if context.products:

            product = (
                context.products[0]
            )

            return {
                "message": (
                    f"{product.title} "
                    f"এর দাম ৳"
                    f"{product.metadata.get('price')}"
                ),
                "products": [
                    product.metadata
                ],
            }

        if context.knowledge:

            result = (
                context.knowledge[0]
            )

            return {
                "message": result.content,
                "products": [],
            }

        return {
            "message": (
                "দুঃখিত, তথ্যটি "
                "খুঁজে পাইনি।"
            ),
            "products": [],
        }
