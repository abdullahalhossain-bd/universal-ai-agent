import re

from app.ai.response_policy import (
    ResponsePolicy,
)

from app.ai.template_response import (
    TemplateResponseGenerator,
)

_FOREIGN_CURRENCY_PATTERN = re.compile(r"[₹$€£]")


def _normalize_currency(text: str) -> str:
    return _FOREIGN_CURRENCY_PATTERN.sub("৳", text)


class ChatResponseService:
    def __init__(self, llm_generator):
        self.llm = llm_generator
        self.policy = ResponsePolicy()
        self.template = TemplateResponseGenerator()

    async def generate(self, query: str, context, plan, agent_config=None):
        use_llm = self.policy.should_use_llm(query=query, context=context, plan=plan)

        if not use_llm:
            if context.product_count:
                products = context.products
                if len(products) == 1:
                    product = products[0]
                    name = getattr(product, "name", "")
                    price = getattr(product, "price", None)
                    stock = getattr(product, "stock", None)
                    message = name
                    if price is not None:
                        message += f" — ৳{float(price):,.0f}"
                    if stock is not None:
                        message += f" | Stock: {float(stock):g}" if stock > 0 else " | Out of stock"
                    return {"message": message, "used_llm": False, "provider": None}
                return {"message": f"{len(products)}টি matching product পাওয়া গেছে।", "used_llm": False, "provider": None}

            if context.knowledge_count:
                knowledge_items = list(context.knowledge)
                if knowledge_items:
                    return {"message": knowledge_items[0].content, "used_llm": False, "provider": None}

            return {"message": "দুঃখিত, এই তথ্যটি খুঁজে পাওয়া যায়নি।", "used_llm": False, "provider": None}

        result = await self.llm.generate(query=query, context=context, agent_config=agent_config)
        return {
            "message": _normalize_currency(result["text"]),
            "used_llm": True,
            "provider": result["provider"],
            "usage": result.get("usage", {}),
        }
