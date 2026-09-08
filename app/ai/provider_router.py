class LLMProviderRouter:

    def __init__(
        self,
        providers: dict,
    ):
        self.providers = providers

    async def generate(
        self,
        messages: list[dict],
        preferred: str | None = None,
    ) -> dict:

        if (
            preferred
            and preferred in self.providers
        ):

            provider = self.providers[
                preferred
            ]

            text = await provider.generate(
                messages=messages
            )

            return {
                "provider": preferred,
                "text": text,
            }

        last_error = None

        for name, provider in (
            self.providers.items()
        ):

            try:

                text = await provider.generate(
                    messages=messages
                )

                return {
                    "provider": name,
                    "text": text,
                }

            except Exception as exc:

                last_error = exc

                continue

        raise RuntimeError(
            "No LLM provider available"
        ) from last_error