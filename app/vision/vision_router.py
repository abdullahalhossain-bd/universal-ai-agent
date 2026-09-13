"""
VisionRouter — the seam between `VisionService` and the actual
vision-capable LLM provider.

Uses the same Groq `/chat/completions` endpoint as the text path
(`app.llm.groq.load_groq_vision_provider`), asking for a strict JSON
response so callers get structured attributes back instead of having
to parse free text. Any provider failure (bad key pool, malformed
JSON, timeout) is normalized into `VisionAnalysisError` so callers
have exactly one exception to handle, regardless of what went wrong
underneath.
"""

from __future__ import annotations

import base64
import json


class VisionAnalysisError(RuntimeError):
    """
    The vision provider call failed or returned something unusable.

    Callers (VisionService) should treat this as a retryable,
    user-facing "temporarily unavailable" condition — never a raw
    500 — and release any budget reservation they took out for the
    attempt.
    """


_PRODUCT_MATCH_PROMPT = (
    "You are a product-vision assistant for an ecommerce store. "
    "Look at the photo and respond with ONLY a JSON object "
    "(no markdown, no commentary) with these exact keys: "
    '"description" (one short sentence describing the item), '
    '"category" (a single lowercase word or short phrase, e.g. '
    '"handbag", "t-shirt", "sneakers"), '
    '"colors" (a list of 1-3 lowercase color words), '
    '"keywords" (a list of 3-6 lowercase search keywords a shopper '
    "might use for this item), "
    '"brand" (a brand name if visible/identifiable, else null).'
)

_IMAGE_QUESTION_PROMPT = (
    "You are a helpful shopping assistant. Look at the photo and "
    "answer the customer's question about it. Respond with ONLY a "
    'JSON object (no markdown, no commentary) with one key: "answer" '
    "(a short, direct answer in plain text)."
)


class VisionRouter:

    async def analyze(
        self,
        image_bytes: bytes,
        mime_type: str,
        task: str,
        question: str | None = None,
    ) -> dict:

        if task == "image_question":
            return await self.answer_about_image(
                image_bytes, mime_type, question
            )

        if task == "product_match":
            return await self.product_match(image_bytes, mime_type)

        return await self.generic_analysis(image_bytes, mime_type)

    async def product_match(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> dict:

        return await self._run(
            image_bytes,
            mime_type,
            _PRODUCT_MATCH_PROMPT,
        )

    async def answer_about_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        question: str | None,
    ) -> dict:

        prompt = _IMAGE_QUESTION_PROMPT

        if question:
            prompt = f"{prompt}\n\nCustomer's question: {question}"

        return await self._run(
            image_bytes,
            mime_type,
            prompt,
        )

    async def generic_analysis(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> dict:

        return await self._run(
            image_bytes,
            mime_type,
            _PRODUCT_MATCH_PROMPT,
        )

    # ---------------------------------
    # Internal
    # ---------------------------------

    async def _run(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
    ) -> dict:

        from app.llm.groq import load_groq_vision_provider

        try:
            provider = load_groq_vision_provider()
        except Exception as exc:
            raise VisionAnalysisError(
                f"Vision provider unavailable: {exc}"
            ) from exc

        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ]

        try:
            raw = await provider.generate(
                messages=messages,
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise VisionAnalysisError(
                f"Vision request failed: {exc}"
            ) from exc

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise VisionAnalysisError(
                f"Vision provider returned invalid JSON: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise VisionAnalysisError(
                "Vision provider returned a non-object JSON payload"
            )

        return parsed
