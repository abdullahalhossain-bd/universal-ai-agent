import re

from typing import Any

import httpx

from app.core.config import settings
from app.llm.base import LLMProvider


class LLMBadRequestError(RuntimeError):
    """
    The LLM request itself is malformed (HTTP 400).

    Rotating API keys cannot fix a bad model name or invalid
    payload, so callers should surface this instead of burning
    through the key pool.
    """


def _classify_status(status_code: int) -> str:
    """
    Classify an HTTP status returned by the provider.

    - "bad_request": malformed request/model/config (HTTP 400).
      Rotating keys will not help.
    - "rotate": the key is invalid/revoked (401), rate limited
      (429), or the provider had a temporary failure (5xx).
      Another key may succeed.
    - "error": any other unexpected status.
    """

    if status_code == 400:
        return "bad_request"

    if status_code in (401, 403, 429):
        return "rotate"

    if status_code >= 500:
        return "rotate"

    return "error"


_BEARER_RE = re.compile(
    r"(Bearer\s+)([^\s,;)}\"]+)",
    re.IGNORECASE,
)


def _sanitize_error_text(text: str) -> str:
    """
    Defense-in-depth: strip anything that looks like an API key
    out of provider error strings before they reach logs.

    `Bearer <token>` sequences are replaced with
    `Bearer ***masked***` — the token itself must never appear
    in logs or surfaced error strings. Long credential-shaped
    runs (32+ hex/base64url chars) are masked as well, in case
    a provider echoes a raw key without the Bearer prefix.
    """

    if not text:
        return ""

    sanitized = _BEARER_RE.sub(
        r"\1***masked***",
        text,
    )

    # Credential-shaped runs that are not preceded by
    # "Bearer" (provider echoing a raw key in a message).
    sanitized = re.sub(
        r"\b[A-Za-z0-9_-]{32,}\b",
        "***masked***",
        sanitized,
    )

    return sanitized


class GroqProvider(LLMProvider):

    def __init__(
        self,
        api_keys: list[str],
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        if not api_keys:
            raise RuntimeError(
                "No Groq API keys configured"
            )

        self.api_keys = api_keys

        self.model = (
            model
            or settings.groq_model
        )

        self.base_url = (
            base_url
            or settings.groq_base_url
        ).rstrip("/")

        self.timeout = timeout

        self._current_key_index = 0

        self._client: httpx.AsyncClient | None = None

        # Usage information from the most recent
        # successful request.
        self.last_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "model": self.model,
        }

        # Useful for internal diagnostics.
        self.last_key_index: int | None = None

    def _get_key(self) -> str:

        return self.api_keys[
            self._current_key_index
        ]

    def _rotate_key(self) -> None:

        self._current_key_index = (
            self._current_key_index + 1
        ) % len(self.api_keys)

    def _get_client(self) -> httpx.AsyncClient:
        """
        Reuse one HTTP client across requests instead of
        opening a new connection pool per call.
        """

        if self._client is None:

            self._client = httpx.AsyncClient(
                timeout=self.timeout,
            )

        return self._client

    async def aclose(self) -> None:

        if self._client is not None:

            await self._client.aclose()

            self._client = None

    def get_last_usage(self) -> dict:

        return dict(
            self.last_usage
        )

    async def generate(
        self,
        messages: list[dict],
        **kwargs: Any,
    ) -> str:

        errors = []

        # Reset usage before a new request so
        # failed requests do not expose stale data.
        self.last_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "model": self.model,
        }

        self.last_key_index = None

        client = self._get_client()

        url = (
            f"{self.base_url}"
            "/chat/completions"
        )

        for _ in range(
            len(self.api_keys)
        ):

            key_index = (
                self._current_key_index
            )

            api_key = self._get_key()

            headers = {
                "Authorization": (
                    f"Bearer {api_key}"
                ),
                "Content-Type": (
                    "application/json"
                ),
            }

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get(
                    "temperature",
                    0.2,
                ),
                "max_tokens": kwargs.get(
                    "max_tokens",
                    500,
                ),
            }

            # Forward optional supported parameters.
            if "top_p" in kwargs:
                payload["top_p"] = kwargs[
                    "top_p"
                ]

            if "seed" in kwargs:
                payload["seed"] = kwargs[
                    "seed"
                ]

            if "response_format" in kwargs:
                payload["response_format"] = kwargs[
                    "response_format"
                ]

            try:

                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

                # ---------------------------------
                # Intelligent failure classification
                # ---------------------------------
                #
                # 400: malformed request/model/config —
                #      rotating keys cannot help, fail fast.
                # 401/403: key invalid/revoked — rotate.
                # 429: rate limited — rotate.
                # 5xx: temporary provider failure — rotate.
                # Timeouts/connection errors — rotate.

                status_code = (
                    response.status_code
                )

                if status_code >= 400:

                    classification = (
                        _classify_status(
                            status_code
                        )
                    )

                    error_body = (
                        response.text[:500]
                        if response.text
                        else ""
                    )

                    if classification == "bad_request":

                        raise LLMBadRequestError(
                            f"Groq rejected the request "
                            f"(HTTP {status_code}): "
                            f"{_sanitize_error_text(error_body)}"
                        )

                    errors.append(
                        f"key_index={key_index}: "
                        f"HTTP {status_code}"
                    )

                    self._rotate_key()

                    continue

                data = response.json()

                # ---------------------------------
                # Usage tracking
                # ---------------------------------

                usage = data.get(
                    "usage",
                    {},
                ) or {}

                input_tokens = int(
                    usage.get(
                        "prompt_tokens",
                        0,
                    )
                    or 0
                )

                output_tokens = int(
                    usage.get(
                        "completion_tokens",
                        0,
                    )
                    or 0
                )

                total_tokens = int(
                    usage.get(
                        "total_tokens",
                        input_tokens
                        + output_tokens,
                    )
                    or 0
                )

                self.last_usage = {
                    "input_tokens": (
                        input_tokens
                    ),
                    "output_tokens": (
                        output_tokens
                    ),
                    "total_tokens": (
                        total_tokens
                    ),
                    "model": data.get(
                        "model",
                        self.model,
                    ),
                }

                self.last_key_index = (
                    key_index
                )

                # ---------------------------------
                # Extract response text
                # ---------------------------------

                choices = data.get(
                    "choices",
                    [],
                )

                if not choices:

                    raise RuntimeError(
                        "Groq response contains "
                        "no choices"
                    )

                message_data = choices[0].get(
                    "message",
                    {},
                )

                content = message_data.get(
                    "content"
                )

                if not isinstance(
                    content,
                    str,
                ):

                    raise RuntimeError(
                        "Groq response contains "
                        "no valid message content"
                    )

                return content

            except LLMBadRequestError:

                # Do not burn the remaining keys on a
                # malformed request.
                raise

            except httpx.TimeoutException as exc:

                errors.append(
                    f"key_index={key_index}: timeout"
                )

                self._rotate_key()

                continue

            except httpx.HTTPError as exc:

                errors.append(
                    f"key_index={key_index}: "
                    f"{type(exc).__name__}"
                )

                self._rotate_key()

                continue

            except Exception as exc:

                errors.append(
                    f"key_index={key_index}: "
                    f"{_sanitize_error_text(str(exc))}"
                )

                self._rotate_key()

        raise RuntimeError(
            "All Groq API keys failed: "
            + " | ".join(errors)
        )


def _collect_api_keys() -> list[str]:

    api_keys = []

    for index in range(1, 15):

        key = getattr(
            settings,
            f"groq_api_key_{index}",
            None,
        )

        if key and key.strip():

            api_keys.append(
                key.strip()
            )

    return api_keys


_provider: GroqProvider | None = None


def load_groq_provider() -> GroqProvider:
    """
    Return the process-wide Groq provider singleton.

    The provider holds the key pool, rotation state and a
    shared HTTP client, so constructing it per request would
    waste connections and reset rotation memory.
    """

    global _provider

    if _provider is not None:
        return _provider

    api_keys = _collect_api_keys()

    if not api_keys:

        raise RuntimeError(
            "No GROQ_API_KEY_* values configured"
        )

    _provider = GroqProvider(
        api_keys=api_keys,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
    )

    return _provider


_vision_provider: GroqProvider | None = None


def load_groq_vision_provider() -> GroqProvider:
    """
    Return the process-wide Groq *vision* provider singleton.

    Same key pool and base URL as the text provider — Groq serves
    both from the same `/chat/completions` endpoint — but pointed
    at `settings.groq_vision_model` instead of `settings.groq_model`,
    since the two are rarely (never, currently) the same model.
    Kept as a separate singleton so `last_usage`/`last_key_index`
    diagnostics for vision calls don't clobber the text provider's.
    """

    global _vision_provider

    if _vision_provider is not None:
        return _vision_provider

    api_keys = _collect_api_keys()

    if not api_keys:

        raise RuntimeError(
            "No GROQ_API_KEY_* values configured"
        )

    _vision_provider = GroqProvider(
        api_keys=api_keys,
        model=settings.groq_vision_model,
        base_url=settings.groq_base_url,
    )

    return _vision_provider


def reset_groq_provider() -> None:
    """
    Test helper: drop the cached singleton.
    """

    global _provider

    _provider = None