import re

from app.ai.intent_models import (
    IntentResult,
    IntentType,
    QueryFilters,
)


class RuleIntentRouter:

    PRODUCT_WORDS = {
        "product",
        "products",
        "item",
        "items",
        "price",
        "দাম",
        "প্রোডাক্ট",
        "পণ্য",
        "জিনিস",
    }

    STOCK_WORDS = {
        "stock",
        "available",
        "availability",
        "স্টক",
        "আছে",
        "available আছে",
    }

    WEBSITE_WORDS = {
        "shipping",
        "delivery",
        "return",
        "refund",
        "policy",
        "about",
        "contact",
        "delivery",
        "shipping",
        "রিটার্ন",
        "রিফান্ড",
        "ডেলিভারি",
        "শিপিং",
        "পলিসি",
        "যোগাযোগ",
    }

    def route(
        self,
        query: str,
    ) -> IntentResult:

        text = query.lower()

        product_score = sum(
            word in text
            for word in self.PRODUCT_WORDS
        )

        stock_score = sum(
            word in text
            for word in self.STOCK_WORDS
        )

        website_score = sum(
            word in text
            for word in self.WEBSITE_WORDS
        )

        intents = []

        if product_score:
            intents.append(
                IntentType.PRODUCT_SEARCH
            )

        if stock_score:
            intents.append(
                IntentType.STOCK_CHECK
            )

        if website_score:
            intents.append(
                IntentType.WEBSITE_KNOWLEDGE
            )

        if not intents:
            intent = IntentType.UNKNOWN

        elif (
            len(intents) > 1
        ):
            intent = IntentType.MIXED

        else:
            intent = intents[0]

        filters = self._extract_filters(
            text
        )

        confidence = min(
            1.0,
            (
                product_score
                + stock_score
                + website_score
            )
            / 3,
        )

        return IntentResult(
            intents=[intent],
            filters=filters,
            confidence=confidence,
        )

    def _extract_filters(
        self,
        text: str,
    ) -> QueryFilters:

        filters = QueryFilters()

        if any(
            word in text
            for word in self.STOCK_WORDS
        ):
            filters.in_stock_only = True

        price_match = re.search(
            r"(?:under|below|less than|নিচে|কম)\s*"
            r"(?:৳|\$)?\s*([\d,]+)",
            text,
        )

        if price_match:

            value = (
                price_match
                .group(1)
                .replace(",", "")
            )

            filters.max_price = float(
                value
            )

        return filters
