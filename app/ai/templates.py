def price_answer(product):

    return (
        f"{product.name}-এর দাম "
        f"{product.currency} "
        f"{product.price}।"
    )


def stock_answer(product):

    if product.in_stock:

        return (
            f"{product.name} বর্তমানে "
            f"stock-এ আছে।"
        )

    return (
        f"{product.name} বর্তমানে "
        f"stock-এ নেই।"
    )
