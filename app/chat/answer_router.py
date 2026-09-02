class AnswerMode:

    TEMPLATE = "template"

    CHEAP_LLM = "cheap_llm"

    SMART_LLM = "smart_llm"


class AnswerRouter:

    def choose(
        self,
        context,
    ):

        message = (
            context.user_message
            .lower()
        )

        # Simple factual questions
        simple_words = {
            "price",
            "stock",
            "delivery",
            "shipping",
            "return",
        }

        if any(
            word in message
            for word in simple_words
        ):

            return AnswerMode.TEMPLATE

        # Complex queries
        if len(message) > 300:

            return AnswerMode.SMART_LLM

        return AnswerMode.CHEAP_LLM
