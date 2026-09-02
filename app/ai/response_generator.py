from app.ai.prompts import (
    RESPONSE_SYSTEM_PROMPT,
)

from app.ai.context_formatter import (
    ContextFormatter,
)


class ResponseGenerator:

    def __init__(
        self,
        provider_router,
    ):

        self.provider_router = (
            provider_router
        )

        self.formatter = (
            ContextFormatter()
        )

    async def generate(
        self,
        query: str,
        context,
    ):

        formatted_context = (
            self.formatter.format(
                context
            )
        )

        history_text = "\n".join(
            f"{item['role']}: "
            f"{item['content']}"
            for item in context.history
        )

        user_prompt = f"""
USER QUESTION:
{query}

AVAILABLE PRODUCT / WEBSITE CONTEXT:
{formatted_context}

RECENT CONVERSATION:
{history_text}

Answer the user naturally and concisely.
Use only the provided context.
"""

        messages = [
            {
                "role": "system",
                "content": (
                    RESPONSE_SYSTEM_PROMPT
                ),
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

        result = await (
            self.provider_router.generate(
                messages=messages
            )
        )

        provider_name = result[
            "provider"
        ]

        text = result["text"]

        usage = {}

        provider = (
            self.provider_router.providers.get(
                provider_name
            )
        )

        if provider is not None and hasattr(
            provider,
            "get_last_usage",
        ):

            usage = provider.get_last_usage()

        return {
            "provider": provider_name,
            "text": text,
            "usage": usage,
        }