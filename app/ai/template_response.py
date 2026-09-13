class TemplateResponseGenerator:

    def product_list(
        self,
        products,
    ):

        if not products:

            return (
                "দুঃখিত, matching "
                "কোনো product পাওয়া যায়নি।"
            )

        if len(products) == 1:

            product = products[0]

            message = (
                f"{product.name}"
            )

            if product.price is not None:

                message += (
                    f" — ৳{product.price:,.0f}"
                )

            if product.stock is not None:

                if product.stock > 0:

                    message += (
                        f" | Stock: "
                        f"{product.stock}"
                    )

                else:

                    message += (
                        " | Out of stock"
                    )

            return message

        return (
            f"{len(products)}টি "
            "matching product পাওয়া গেছে।"
        )


class KnowledgeTemplateGenerator:

    def generate(
        self,
        results,
    ):

        if not results:

            return (
                "দুঃখিত, এই তথ্যটি "
                "খুঁজে পাওয়া যায়নি।"
            )

        top = results[0]

        return top.content
