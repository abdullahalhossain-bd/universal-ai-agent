import inspect

from app.search.learning import (
    correction_matches_store,
    get_learned_correction,
    save_learned_correction,
)


class LLMProviderRouter:

    def __init__(
        self,
        providers: dict,
    ):
        self.providers = providers

    @staticmethod
    def _search_learning_context():
        """Return ChatService DB/store context when this is the typo fallback."""
        frame = inspect.currentframe()
        try:
            while frame is not None:
                if frame.f_code.co_name == "_llm_correct_search_term":
                    owner = frame.f_locals.get("self")
                    store_id = frame.f_locals.get("store_id")
                    raw_text = frame.f_locals.get("raw_text")
                    db = getattr(owner, "db", None)
                    if db is not None and store_id and raw_text:
                        return db, str(store_id), str(raw_text)
                frame = frame.f_back
        finally:
            del frame
        return None

    async def generate(
        self,
        messages: list[dict],
        preferred: str | None = None,
    ) -> dict:

        learning_context = self._search_learning_context()
        if learning_context:
            db, store_id, raw_text = learning_context
            cached = get_learned_correction(db, store_id, raw_text)
            if cached and correction_matches_store(db, store_id, cached):
                return {
                    "provider": "search_learning_cache",
                    "text": cached,
                    "cached": True,
                }

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

            if learning_context:
                db, store_id, raw_text = learning_context
                if correction_matches_store(db, store_id, text):
                    save_learned_correction(
                        db, store_id, raw_text, text, source="groq"
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

                if learning_context:
                    db, store_id, raw_text = learning_context
                    if correction_matches_store(db, store_id, text):
                        save_learned_correction(
                            db, store_id, raw_text, text, source="groq"
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