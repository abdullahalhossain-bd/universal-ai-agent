from app.query_engine.intent import Intent
from app.query_engine.entities import extract_entities
from app.query_engine.plan import QueryPlan, PlanStep


def detect_intent(
    message: str,
    has_image: bool = False,
):

    text = message.lower()

    if has_image:
        return Intent.IMAGE_SEARCH

    if "দাম" in text or "price" in text:
        return Intent.PRICE

    if "stock" in text or "আছে" in text:
        return Intent.STOCK

    if (
        "policy" in text
        or "delivery" in text
        or "return" in text
        or "warranty" in text
    ):
        return Intent.WEBSITE_QA

    if "দেখাও" in text or "show" in text:
        return Intent.PRODUCT_SEARCH

    return Intent.UNKNOWN


def build_plan(
    message: str,
    has_image: bool = False,
):

    intent = detect_intent(message, has_image)

    entities = extract_entities(message)

    steps = []

    if has_image:

        steps.append(
            PlanStep(tool="image_analysis")
        )

    if intent in (
        Intent.PRODUCT_SEARCH,
        Intent.IMAGE_SEARCH,
        Intent.PRICE,
        Intent.STOCK,
    ):

        steps.append(
            PlanStep(
                tool="product_search",
                filters={
                    k: v
                    for k, v in entities.items()
                    if v is not None
                },
            )
        )

    if intent == Intent.STOCK:

        steps.append(
            PlanStep(tool="stock")
        )

    if intent == Intent.WEBSITE_QA:

        steps.append(
            PlanStep(
                tool="knowledge_search",
                query=message,
            )
        )

    return QueryPlan(
        intent=intent.value,
        steps=steps,
    )
