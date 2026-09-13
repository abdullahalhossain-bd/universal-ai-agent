class LLMRouter:

    def __init__(
        self,
        cheap_provider,
        smart_provider,
    ):

        self.cheap = cheap_provider
        self.smart = smart_provider

    async def generate(
        self,
        mode,
        messages,
    ):

        if mode == "smart_llm":

            return await self.smart.generate(
                messages
            )

        return await self.cheap.generate(
            messages
        )
