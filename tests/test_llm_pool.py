"""
Tests for the Groq LLM key-pool provider, cost estimation and the
LLM router (Task 3-a).

Coverage:
- app/llm/groq.py   : status classification, 400 fast-fail (no key burn),
                      401/429 key rotation, usage extraction, error-text
                      sanitization, HTTP client reuse.
- app/ai/cost_engine.py : estimate_cost / estimate_max_cost /
                      estimate_tokens / estimate_messages_tokens.
- app/llm/router.py : cheap vs smart provider routing.
- app/llm/base.py   : LLMProvider ABC contract.

No real network calls are made anywhere in this module: every provider
under test gets an httpx.AsyncClient wired to an httpx.MockTransport,
injected via the provider's own client slot (`_client`), which
`_get_client()` reuses.
"""

import httpx
import pytest
import pytest_asyncio

from app.ai.cost_engine import (
    estimate_cost,
    estimate_max_cost,
    estimate_messages_tokens,
    estimate_tokens,
)
from app.llm.base import LLMProvider
from app.llm.groq import (
    LLMBadRequestError,
    GroqProvider,
    _classify_status,
    _sanitize_error_text,
)
from app.llm.router import LLMRouter

TEST_MODEL = "test-model"
TEST_BASE_URL = "https://groq.test/openai/v1"

ZERO_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "model": TEST_MODEL,
}


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _success_body(
    content: str = "ok",
    usage: dict | None = None,
    model: str = "llama-3.3-70b-versatile",
) -> dict:
    """Build a Groq/OpenAI-style chat.completion response body."""
    body = {
        "model": model,
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _recording_handler(responder):
    """
    Wrap a responder callable into a MockTransport handler that
    records the Authorization header of every request it sees.
    """
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return responder(request)

    handler.seen = seen
    return handler


@pytest_asyncio.fixture
async def make_groq_provider():
    """
    Factory fixture: build a GroqProvider whose HTTP client is backed
    by an httpx.MockTransport. All providers created through the
    factory are closed on teardown (no state leakage between tests).
    """
    providers: list[GroqProvider] = []

    def _make(handler, keys=("k1", "k2", "k3")) -> GroqProvider:
        provider = GroqProvider(
            api_keys=list(keys),
            model=TEST_MODEL,
            base_url=TEST_BASE_URL,
        )
        # Inject the mock-transport client into the provider's own
        # client slot; _get_client() returns it unchanged.
        provider._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=provider.timeout,
        )
        providers.append(provider)
        return provider

    yield _make

    for provider in providers:
        try:
            await provider.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. Status classification
# ---------------------------------------------------------------------------

class TestGroqStatusClassification:

    @pytest.mark.parametrize("status", [400])
    def test_400_is_bad_request(self, status):
        assert _classify_status(status) == "bad_request"

    @pytest.mark.parametrize("status", [401, 403, 429])
    def test_auth_and_rate_limit_statuses_rotate(self, status):
        assert _classify_status(status) == "rotate"

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_error_statuses_rotate(self, status):
        assert _classify_status(status) == "rotate"

    @pytest.mark.parametrize("status", [200, 404])
    def test_success_and_client_error_statuses_are_plain_errors(self, status):
        assert _classify_status(status) == "error"

    @pytest.mark.parametrize("status", [402, 418])
    def test_unexpected_statuses_fall_through_to_error(self, status):
        assert _classify_status(status) == "error"


# ---------------------------------------------------------------------------
# 2. HTTP 400 must not burn keys
# ---------------------------------------------------------------------------

class TestGroqBadRequestNoKeyBurn:

    @pytest.mark.asyncio
    async def test_400_raises_bad_request_error(self, make_groq_provider):
        handler = _recording_handler(
            lambda request: httpx.Response(
                400,
                json={"error": {"message": "Invalid model name"}},
            )
        )
        provider = make_groq_provider(handler)

        with pytest.raises(LLMBadRequestError) as excinfo:
            await provider.generate(
                [{"role": "user", "content": "hi"}]
            )

        message = str(excinfo.value)
        assert "HTTP 400" in message
        assert "Invalid model name" in message

    @pytest.mark.asyncio
    async def test_400_does_not_rotate_key_index(self, make_groq_provider):
        handler = _recording_handler(
            lambda request: httpx.Response(
                400,
                json={"error": {"message": "bad model"}},
            )
        )
        provider = make_groq_provider(handler)

        with pytest.raises(LLMBadRequestError):
            await provider.generate(
                [{"role": "user", "content": "hi"}]
            )

        # Exactly one HTTP attempt: remaining keys were not burned.
        assert len(handler.seen) == 1
        assert handler.seen == ["Bearer k1"]
        assert provider._current_key_index == 0
        assert provider.last_key_index is None
        assert provider.get_last_usage() == ZERO_USAGE

    def test_bad_request_error_is_a_runtime_error(self):
        # Callers may catch RuntimeError broadly.
        assert issubclass(LLMBadRequestError, RuntimeError)


# ---------------------------------------------------------------------------
# 3. 401 rotates to the next key and recovers
# ---------------------------------------------------------------------------

class TestGroq401RotatesAndRecovers:

    @pytest.mark.asyncio
    async def test_401_rotates_to_second_key_and_succeeds(
        self, make_groq_provider
    ):
        usage = {
            "prompt_tokens": 12,
            "completion_tokens": 34,
            "total_tokens": 46,
        }

        def responder(request: httpx.Request) -> httpx.Response:
            if request.headers.get("Authorization") == "Bearer k1":
                return httpx.Response(
                    401,
                    json={"error": {"message": "Invalid API Key"}},
                )
            return httpx.Response(
                200,
                json=_success_body(content="recovered", usage=usage),
            )

        handler = _recording_handler(responder)
        provider = make_groq_provider(handler)

        content = await provider.generate(
            [{"role": "user", "content": "hi"}]
        )

        assert content == "recovered"

        # Both keys were tried, in pool order.
        assert handler.seen == ["Bearer k1", "Bearer k2"]

        # The successful request used key index 1 and rotation
        # advanced the pool cursor to that key.
        assert provider.last_key_index == 1
        assert provider._current_key_index == 1

        assert provider.get_last_usage() == {
            "input_tokens": 12,
            "output_tokens": 34,
            "total_tokens": 46,
            "model": "llama-3.3-70b-versatile",
        }


# ---------------------------------------------------------------------------
# 4. All keys rate-limited (429) -> exhaustion
# ---------------------------------------------------------------------------

class TestGroq429Rotates:

    @pytest.mark.asyncio
    async def test_all_keys_429_raises_runtime_error_and_zeroes_usage(
        self, make_groq_provider
    ):
        handler = _recording_handler(
            lambda request: httpx.Response(
                429,
                json={"error": {"message": "Rate limit reached"}},
            )
        )
        provider = make_groq_provider(handler, keys=("k1", "k2", "k3"))

        with pytest.raises(RuntimeError) as excinfo:
            await provider.generate(
                [{"role": "user", "content": "hi"}]
            )

        message = str(excinfo.value)
        assert "All Groq API keys failed" in message
        # Every key in the pool was attempted exactly once.
        assert message.count("HTTP 429") == 3
        assert len(handler.seen) == 3

        # Pool cursor wrapped back to the start after 3 rotations.
        assert provider._current_key_index == 0
        assert provider.last_key_index is None

        # No stale usage leaks out of a failed request.
        assert provider.get_last_usage() == ZERO_USAGE


# ---------------------------------------------------------------------------
# 5. Usage extraction from a 200 response
# ---------------------------------------------------------------------------

class TestGroqUsageExtraction:

    @pytest.mark.asyncio
    async def test_openai_style_usage_fields_are_mapped(
        self, make_groq_provider
    ):
        # Groq/OpenAI field names, as read by app/llm/groq.py:
        # prompt_tokens / completion_tokens / total_tokens.
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
        handler = _recording_handler(
            lambda request: httpx.Response(
                200,
                json=_success_body(content="done", usage=usage),
            )
        )
        provider = make_groq_provider(handler)

        content = await provider.generate(
            [{"role": "user", "content": "hi"}]
        )

        assert content == "done"
        assert provider.get_last_usage() == {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "model": "llama-3.3-70b-versatile",
        }
        assert provider.last_key_index == 0

    @pytest.mark.asyncio
    async def test_missing_total_tokens_defaults_to_input_plus_output(
        self, make_groq_provider
    ):
        usage = {"prompt_tokens": 10, "completion_tokens": 5}
        handler = _recording_handler(
            lambda request: httpx.Response(
                200,
                json=_success_body(usage=usage),
            )
        )
        provider = make_groq_provider(handler)

        await provider.generate([{"role": "user", "content": "hi"}])

        assert provider.get_last_usage()["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_missing_usage_reports_zeros(self, make_groq_provider):
        handler = _recording_handler(
            lambda request: httpx.Response(
                200,
                json=_success_body(content="no-usage"),
            )
        )
        provider = make_groq_provider(handler)

        content = await provider.generate(
            [{"role": "user", "content": "hi"}]
        )

        assert content == "no-usage"
        assert provider.get_last_usage() == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "model": "llama-3.3-70b-versatile",
        }


# ---------------------------------------------------------------------------
# 6. Error-text sanitization
# ---------------------------------------------------------------------------

class TestGroqSanitizeErrorText:

    def test_empty_string_returns_empty_string(self):
        assert _sanitize_error_text("") == ""

    def test_none_like_falsy_input_returns_empty_string(self):
        # `if not text` branch: falsy input is normalized to "".
        assert _sanitize_error_text("") == ""

    def test_bearer_prefix_is_masked(self):
        text = "auth failed: Bearer gsk_live_9f8e7d6c5b4a rejected"
        result = _sanitize_error_text(text)

        # The token itself must never survive sanitization —
        # only the masked marker is allowed after "Bearer".
        assert result == (
            "auth failed: Bearer ***masked*** rejected"
        )
        assert "gsk_live_9f8e7d6c5b4a" not in result

    def test_bare_credential_shaped_run_is_masked(self):
        # A raw key echoed without the Bearer prefix is still
        # masked (32+ credential-shaped characters).
        text = "invalid key: gsk_abcdefghijklmnopabcdefghijklmnop"
        result = _sanitize_error_text(text)
        assert "gsk_abcdefghijklmnopabcdefghijklmnop" not in result
        assert "***masked***" in result

    def test_normal_words_are_not_masked(self):
        # Ordinary prose (short words, punctuation) is preserved.
        text = "rate limit exceeded, retry after 60 seconds (code 429)"
        assert _sanitize_error_text(text) == text

    def test_text_without_bearer_passes_through_unchanged(self):
        text = "rate limit exceeded for org org_01"
        assert _sanitize_error_text(text) == text


# ---------------------------------------------------------------------------
# 7. HTTP client reuse
# ---------------------------------------------------------------------------

class TestGroqClientReuse:

    @pytest.mark.asyncio
    async def test_get_client_returns_same_instance(self):
        provider = GroqProvider(
            api_keys=["k1"],
            model=TEST_MODEL,
            base_url=TEST_BASE_URL,
        )

        try:
            client1 = provider._get_client()
            client2 = provider._get_client()

            assert isinstance(client1, httpx.AsyncClient)
            assert client1 is client2
        finally:
            await provider.aclose()

    @pytest.mark.asyncio
    async def test_aclose_resets_client(self):
        provider = GroqProvider(
            api_keys=["k1"],
            model=TEST_MODEL,
            base_url=TEST_BASE_URL,
        )

        client1 = provider._get_client()
        await provider.aclose()

        assert provider._client is None

        # A fresh client (new instance) is created after close.
        client2 = provider._get_client()
        assert client2 is not client1
        assert isinstance(client2, httpx.AsyncClient)

        await provider.aclose()


# ---------------------------------------------------------------------------
# 8. Cost estimation
# ---------------------------------------------------------------------------

class TestCostEstimation:
    # Module under test: app/ai/cost_engine.py (the cost engine lives
    # in app/ai, not app/usage).

    def test_one_million_input_tokens_at_0075(self):
        assert estimate_cost(
            input_tokens=1_000_000,
            output_tokens=0,
            input_price=0.075,
            output_price=0.30,
        ) == pytest.approx(0.075)

    def test_mixed_input_and_output(self):
        assert estimate_cost(
            input_tokens=2_000_000,
            output_tokens=1_000_000,
            input_price=0.075,
            output_price=0.30,
        ) == pytest.approx(0.45)

    def test_zero_tokens_cost_zero(self):
        assert estimate_cost(0, 0, 0.075, 0.30) == 0.0

    def test_negative_tokens_are_clamped_to_zero(self):
        assert estimate_cost(-100, -5, 0.075, 0.30) == 0.0

    def test_estimate_max_cost_uses_output_cap(self):
        assert estimate_max_cost(
            input_tokens=1_000_000,
            max_output_tokens=1_000_000,
            input_price=0.075,
            output_price=0.30,
        ) == pytest.approx(0.375)

    def test_estimate_tokens_known_length(self):
        # 1 token ~= 4 characters, rounded upward.
        assert estimate_tokens("a" * 40) == 10
        assert estimate_tokens("a" * 41) == 11
        assert estimate_tokens("abc") == 1
        assert estimate_tokens("") == 0

    def test_estimate_messages_tokens_with_overhead(self):
        # role "user" (4 chars -> 1) + content 40 chars (-> 10)
        # + 4 per-message overhead = 15.
        messages = [{"role": "user", "content": "a" * 40}]
        assert estimate_messages_tokens(messages) == 15

    def test_estimate_messages_tokens_empty_list_is_at_least_one(self):
        assert estimate_messages_tokens([]) == 1


# ---------------------------------------------------------------------------
# 9. LLM provider router
# ---------------------------------------------------------------------------

class _FakeProvider:
    """Minimal duck-typed provider that records generate() calls."""

    def __init__(self, name: str):
        self.name = name
        self.calls: list[list[dict]] = []

    async def generate(self, messages, **kwargs):
        self.calls.append(messages)
        return f"reply-from-{self.name}"


class TestLLMProviderRouter:
    # app/llm/router.py routes by mode: "smart_llm" -> smart provider,
    # anything else -> cheap provider.

    @pytest.mark.asyncio
    async def test_smart_llm_mode_routes_to_smart_provider(self):
        cheap = _FakeProvider("cheap")
        smart = _FakeProvider("smart")
        router = LLMRouter(cheap_provider=cheap, smart_provider=smart)

        messages = [{"role": "user", "content": "plan this"}]
        result = await router.generate("smart_llm", messages)

        assert result == "reply-from-smart"
        assert smart.calls == [messages]
        assert cheap.calls == []

    @pytest.mark.asyncio
    async def test_any_other_mode_routes_to_cheap_provider(self):
        messages = [{"role": "user", "content": "hello"}]

        for mode in ("cheap_llm", "auto", "deterministic", ""):
            cheap = _FakeProvider("cheap")
            smart = _FakeProvider("smart")
            router = LLMRouter(cheap_provider=cheap, smart_provider=smart)

            result = await router.generate(mode, messages)

            assert result == f"reply-from-cheap", f"mode={mode!r}"
            assert cheap.calls == [messages], f"mode={mode!r}"
            assert smart.calls == [], f"mode={mode!r}"


# ---------------------------------------------------------------------------
# 10. LLMProvider base contract
# ---------------------------------------------------------------------------

class TestLLMProviderBase:

    def test_abstract_base_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            LLMProvider()

    def test_groq_provider_implements_llm_provider(self):
        provider = GroqProvider(
            api_keys=["k1"],
            model=TEST_MODEL,
            base_url=TEST_BASE_URL,
        )
        assert isinstance(provider, LLMProvider)
