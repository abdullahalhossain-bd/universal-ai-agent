from app.responses.models import (
    ProductCard,
)


def product_to_card(
    product,
) -> ProductCard:

    return ProductCard(
        id=product.id,
        name=product.name,
        price=(
            float(product.price)
            if product.price is not None
            else None
        ),
        currency=product.currency,
        stock=(
            float(product.stock)
            if product.stock is not None
            else None
        ),
        image_url=product.image_url,
        product_url=product.product_url,
        brand=product.brand,
        category=product.category,
    )


def compose_product_search(
    products,
    max_price=None,
):

    count = len(products)

    if count == 0:

        if max_price:

            message = (
                f"দুঃখিত, {max_price:.0f} "
                "টাকার মধ্যে কোনো product "
                "পাওয়া যায়নি।"
            )

        else:

            message = (
                "দুঃখিত, matching কোনো "
                "product পাওয়া যায়নি।"
            )

        return message

    if max_price:

        return (
            f"অবশ্যই! {max_price:.0f} "
            f"টাকার মধ্যে {count}টি "
            "product পাওয়া গেছে।"
        )

    return (
        f"অবশ্যই! {count}টি "
        "matching product পাওয়া গেছে।"
    )


def compose_response(
    intent,
    products,
    max_price=None,
):

    if intent == "product_search":

        cards = [
            product_to_card(product)
            for product in products
        ]

        message = compose_product_search(
            products,
            max_price,
        )

        return {
            "message": message,
            "intent": intent,
            "products": [
                card.model_dump()
                for card in cards
            ],
            "metadata": {
                "count": len(cards)
            },
        }

    return {
        "message": (
            "আমি আপনার প্রশ্নটি "
            "বুঝতে চেষ্টা করছি।"
        ),
        "intent": intent,
        "products": [],
        "metadata": {},
    }
