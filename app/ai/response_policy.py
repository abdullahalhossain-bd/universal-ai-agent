class ResponsePolicy:

    def should_use_llm(
        self,
        query: str,
        context,
        plan,
    ) -> bool:

        # No grounded context -> do not call the LLM.
        if not context.items:
            return False

        intent = getattr(
            plan,
            "intent",
            None,
        )

        intent_value = getattr(
            intent,
            "value",
            str(intent)
            if intent is not None
            else "unknown",
        )

        query_lower = query.lower()

        # ---------------------------------
        # Simple product queries
        # ---------------------------------
        #
        # Product listing / price / stock are
        # deterministic and should cost $0.
        #

        if intent_value == "product_search":

            simple_words = {
                "দাম",
                "মূল্য",
                "price",
                "cost",
                "কত",
                "stock",
                "স্টক",
                "available",
                "আছে",
            }

            if any(
                word in query_lower
                for word in simple_words
            ):
                return False

            if context.product_count:
                return False

        # ---------------------------------
        # Simple knowledge queries
        # ---------------------------------

        if (
            intent_value
            == "knowledge_search"
            and context.knowledge_count
        ):
            return False

        # ---------------------------------
        # Mixed queries
        # ---------------------------------
        #
        # Product + website information usually
        # benefits from one grounded natural answer.
        #

        if intent_value == "mixed":

            return bool(
                context.product_count
                or context.knowledge_count
            )

        # ---------------------------------
        # Unknown but grounded
        # ---------------------------------

        if intent_value == "unknown":

            return bool(
                context.product_count
                or context.knowledge_count
            )

        return False