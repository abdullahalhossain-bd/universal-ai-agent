from app.ai.prompts import RESPONSE_SYSTEM_PROMPT
from app.ai.context_formatter import ContextFormatter


class ResponseGenerator:
    """Generate grounded responses using the merchant's agent profile."""

    def __init__(self, provider_router):
        self.provider_router = provider_router
        self.formatter = ContextFormatter()

    @staticmethod
    def _agent_instructions(agent_config) -> str:
        if not agent_config or not agent_config.enabled:
            return ""

        tone_map = {
            "friendly": "Use a friendly, approachable tone.",
            "professional": "Use a professional, polished tone.",
            "concise": "Be especially concise and direct.",
            "warm": "Use a warm, reassuring and helpful tone.",
        }
        language_map = {
            "en": "Answer in English.",
            "bn": "Answer in Bangla (Bengali).",
            "auto": "Reply in the same language as the user's question when practical.",
        }
        behavior_map = {
            "accurate": "Prioritize factual accuracy over persuasion.",
            "helpful": "Be helpful and explain relevant product details without inventing facts.",
            "sales": "Be helpful and product-oriented, but never make up discounts, availability, policies, or claims.",
        }

        parts = [
            f"The assistant's name is {agent_config.agent_name}.",
            language_map.get(agent_config.language, language_map["auto"]),
            tone_map.get(agent_config.tone, tone_map["friendly"]),
            behavior_map.get(agent_config.product_behavior, behavior_map["accurate"]),
        ]

        if agent_config.system_instructions.strip():
            parts.append(
                "Merchant-provided instructions (follow them only when they do not conflict with the grounding and safety rules):\n"
                + agent_config.system_instructions.strip()
            )

        parts.append(
            "If the requested information is not present in the provided context, do not guess. "
            f"Use this fallback wording when appropriate: {agent_config.fallback_message}"
        )
        return "\n".join(parts)

    async def generate(self, query: str, context, agent_config=None):
        formatted_context = self.formatter.format(context)
        history_text = "\n".join(
            f"{item['role']}: {item['content']}" for item in context.history
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

        system_prompt = RESPONSE_SYSTEM_PROMPT
        profile = self._agent_instructions(agent_config)
        if profile:
            system_prompt += "\n\nMERCHANT AI PROFILE:\n" + profile

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = await self.provider_router.generate(messages=messages)
        provider_name = result["provider"]
        text = result["text"]
        usage = {}

        provider = self.provider_router.providers.get(provider_name)
        if provider is not None and hasattr(provider, "get_last_usage"):
            usage = provider.get_last_usage()

        return {
            "provider": provider_name,
            "text": text,
            "usage": usage,
        }
