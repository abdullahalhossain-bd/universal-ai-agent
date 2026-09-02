"""
Integration tests for the chat / knowledge / isolation surface
(Universal Commerce AI API — Task 3-c).

Coverage map (one class per concern):

1.  TestHistoryWindow          ChatService._load_history keeps the LATEST
                               20 messages in chronological order.
2.  TestSessionRaceIntegrity   _get_or_create_session + unique constraint
                               uq_chat_sessions_store_conversation.
3.  TestCrossStoreIsolation    Sessions and product searches are strictly
                               store-scoped.
4.  TestDeterministicNoLLM     A pure greeting never builds/uses the LLM
                               stack (Groq) and still answers in Bangla.
5.  TestBudgetExhaustedMessage A mixed query with monthly_budget = 0 is
                               blocked by the budget reservation and returns
                               the Bangla "usage limit" message.
6.  TestSSRFGuard              app/knowledge/crawler.py URL validation
                               (local checks only — no network fetches).
7.  TestKnowledgeIsolation     Keyword knowledge search is store-scoped
                               (KnowledgeSearchEngine — no sentence_transformers
                               needed; pgvector is disabled in this DB, the
                               embedding column is Text).
8.  TestAuthDivergence         authenticate_api_key: missing key, wrong
                               prefix, valid pk_ key, revoked key.

Rules respected by this file:
- NO real external calls: the shared LLM stack is monkeypatched to raise
  AssertionError wherever a test touches a code path that could reach it;
  rate limiting lives in the HTTP router, which these tests deliberately
  bypass by calling the service layer directly (Redis state never involved).
- DB hygiene: every test creates its own stores with uuid-suffixed names;
  teardown deletes children (chat_messages, chat_sessions, usage_records,
  knowledge_chunks, knowledge_pages, api_keys, products) BEFORE stores and
  never touches rows belonging to other stores.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from tests.markers import requires_postgres

pytestmark = requires_postgres
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import authenticate_api_key
from app.chat.models import ChatMessage, ChatSession
from app.chat.schemas import ChatRequest
from app.chat.service import ChatService
from app.core.config import settings
from app.core.security import hash_api_key
from app.db.database import SessionLocal
from app.db.models import APIKey, Product, Store
from app.knowledge.chunk import KnowledgeChunk, KnowledgePage
from app.knowledge.crawler import assert_safe_url, is_private_host
from app.knowledge.search import KnowledgeSearchEngine
from app.usage.models import UsageRecord


# ---------------------------------
# Shared helpers
# ---------------------------------

def forbid_llm_stack(monkeypatch) -> None:
    """
    Replace ChatService._shared_llm_stack with a sentinel that fails the
    test the moment ANY code path tries to build or use the Groq pipeline.

    This guarantees both (a) the deterministic-path assertions are
    meaningful and (b) no real external LLM call can ever be made.
    """

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "LLM stack must not be built or invoked on this code path"
        )

    monkeypatch.setattr(
        ChatService,
        "_shared_llm_stack",
        classmethod(_forbidden),
    )


class IsolatedStoreTestBase:
    """
    Base class for DB-backed tests.

    Provides a real SessionLocal session plus a store factory that tracks
    every created store id. Teardown removes all child rows for the tracked
    stores (children first, store last) and nothing else.
    """

    @pytest.fixture(autouse=True)
    def _isolated_db(self):
        self._db: Session = SessionLocal()
        self._store_ids: list[str] = []
        yield
        try:
            self._cleanup_tracked_stores()
        finally:
            self._db.close()

    # -- factories -------------------------------------------------

    def make_store(
        self,
        *,
        monthly_budget: float = 5.0,
        name: str | None = None,
        status: str = "active",
    ) -> Store:
        store = Store(
            name=name or f"store-{uuid.uuid4().hex[:12]}",
            monthly_budget=monthly_budget,
            status=status,
        )
        self._db.add(store)
        self._db.commit()
        self._db.refresh(store)
        self._store_ids.append(store.id)
        return store

    def make_chat_session(
        self,
        store: Store,
        conversation_key: str | None = None,
    ) -> ChatSession:
        session = ChatSession(
            id=str(uuid.uuid4()),
            store_id=store.id,
            conversation_key=conversation_key
            or f"conv-{uuid.uuid4().hex}",
            visitor_id="pytest",
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def make_product(
        self,
        store: Store,
        name: str,
        *,
        price: float = 100.0,
        stock: float = 3.0,
    ) -> Product:
        product = Product(
            id=f"prod-{uuid.uuid4().hex[:16]}",
            store_id=store.id,
            name=name,
            price=price,
            stock=stock,
        )
        self._db.add(product)
        self._db.commit()
        return product

    # -- teardown --------------------------------------------------

    def _cleanup_tracked_stores(self) -> None:
        """
        Delete all rows belonging to the stores created by this test,
        children before parents. Never touches other stores.
        """
        if not self._store_ids:
            self._db.rollback()
            return

        db = self._db

        db.query(ChatMessage).filter(
            ChatMessage.session_id.in_(
                db.query(ChatSession.id).filter(
                    ChatSession.store_id.in_(self._store_ids)
                )
            )
        ).delete(synchronize_session=False)

        db.query(ChatSession).filter(
            ChatSession.store_id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.query(UsageRecord).filter(
            UsageRecord.store_id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.query(KnowledgeChunk).filter(
            KnowledgeChunk.store_id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.query(KnowledgePage).filter(
            KnowledgePage.store_id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.query(APIKey).filter(
            APIKey.store_id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.query(Product).filter(
            Product.store_id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.query(Store).filter(
            Store.id.in_(self._store_ids)
        ).delete(synchronize_session=False)

        db.commit()
        db.expire_all()


# ---------------------------------
# 1. History window
# ---------------------------------

class TestHistoryWindow(IsolatedStoreTestBase):
    """
    ChatService._load_history must return the LATEST 20 messages of a
    conversation in chronological (ascending created_at) order.

    Regression guard: the original implementation ordered ASC + LIMIT 20,
    which kept the OLDEST 20 messages and silently lost recent context.
    """

    TOTAL_MESSAGES = 25

    def _seed_conversation(self, session_id: str) -> None:
        # Explicit, strictly increasing timestamps: identical server-side
        # defaults inside one fast loop could collide to the same microsecond
        # and make the ordering assertion flaky.
        base = datetime(2024, 1, 1, 12, 0, 0)

        for i in range(self.TOTAL_MESSAGES):
            self._db.add(
                ChatMessage(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"msg-{i:02d}",
                    created_at=base + timedelta(seconds=i),
                )
            )

        # Non-chat roles must never leak into the model history.
        self._db.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role="system",
                content="msg-system",
                created_at=base - timedelta(seconds=60),
            )
        )
        self._db.commit()

    def test_load_history_returns_latest_20_in_chronological_order(self):
        store = self.make_store()
        chat_session = self.make_chat_session(store)
        self._seed_conversation(chat_session.id)

        service = ChatService(self._db)

        history = service._load_history(chat_session.id)

        assert isinstance(history, list)
        assert len(history) == 20

        # The window must be the LATEST 20 messages (05..24), NOT the
        # oldest 20 (00..19).
        contents = [item["content"] for item in history]
        assert contents == [f"msg-{i:02d}" for i in range(5, 25)]

        # Chronological ascending inside the window.
        assert history[0]["content"] == "msg-05"
        assert history[-1]["content"] == "msg-24"

    def test_load_history_excludes_non_chat_roles(self):
        store = self.make_store()
        chat_session = self.make_chat_session(store)
        self._seed_conversation(chat_session.id)

        history = ChatService(self._db)._load_history(chat_session.id)

        contents = [item["content"] for item in history]
        assert "msg-system" not in contents
        assert all(
            item["role"] in ("user", "assistant") for item in history
        )

    def test_load_history_item_shape(self):
        store = self.make_store()
        chat_session = self.make_chat_session(store)
        self._seed_conversation(chat_session.id)

        history = ChatService(self._db)._load_history(chat_session.id)

        assert all(set(item.keys()) == {"role", "content"} for item in history)
        assert all(
            item["role"] == ("user" if int(item["content"].split("-")[1]) % 2 == 0 else "assistant")
            for item in history
        )


# ---------------------------------
# 2. Session race integrity
# ---------------------------------

class TestSessionRaceIntegrity(IsolatedStoreTestBase):
    """
    Concurrent creation of the same (store_id, conversation_key) must not
    raise and must yield exactly ONE chat_sessions row. The DB-level
    unique constraint uq_chat_sessions_store_conversation is the arbiter;
    the IntegrityError handler in _get_or_create_session converts the
    loser's INSERT into a re-select of the winner's row.
    """

    def test_concurrent_same_key_creates_exactly_one_row(self):
        store = self.make_store()
        conversation_key = f"conv-{uuid.uuid4().hex}"

        barrier = threading.Barrier(2, timeout=15)
        results: list[str] = []
        errors: list[Exception] = []

        def worker() -> None:
            own_db = SessionLocal()
            try:
                # Both workers line up here so their SELECTs/INSERTs
                # overlap as tightly as the scheduler allows.
                barrier.wait()
                service = ChatService(own_db)
                session = service._get_or_create_session(
                    store.id, conversation_key
                )
                results.append(session.id)
            except Exception as exc:  # surfaced by the assertions below
                errors.append(exc)
            finally:
                own_db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            for future in futures:
                future.result(timeout=30)

        assert errors == [], f"concurrent creation raised: {errors!r}"
        assert len(results) == 2
        assert results[0] == results[1], (
            "both racers must resolve to the same winning session row"
        )

        rows = (
            self._db.query(ChatSession)
            .filter(
                ChatSession.store_id == store.id,
                ChatSession.conversation_key == conversation_key,
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].id == results[0]

    def test_sequential_repeat_calls_return_same_session(self):
        store = self.make_store()
        conversation_key = f"conv-{uuid.uuid4().hex}"

        service = ChatService(self._db)

        first = service._get_or_create_session(store.id, conversation_key)
        second = service._get_or_create_session(store.id, conversation_key)

        assert first.id == second.id
        assert first.store_id == store.id

        rows = (
            self._db.query(ChatSession)
            .filter(ChatSession.store_id == store.id)
            .all()
        )
        assert len(rows) == 1

    def test_same_key_different_stores_are_distinct_rows(self):
        store_a = self.make_store()
        store_b = self.make_store()
        conversation_key = f"conv-{uuid.uuid4().hex}"

        service = ChatService(self._db)

        session_a = service._get_or_create_session(store_a.id, conversation_key)
        session_b = service._get_or_create_session(store_b.id, conversation_key)

        assert session_a.id != session_b.id
        assert session_a.store_id == store_a.id
        assert session_b.store_id == store_b.id


# ---------------------------------
# 3. Cross-store isolation
# ---------------------------------

class TestCrossStoreIsolation(IsolatedStoreTestBase):
    """
    Identical conversation_keys across stores and identically-named
    products across stores must never leak across the tenant boundary.
    """

    def test_session_lookup_returns_own_store_session_only(self):
        store_a = self.make_store()
        store_b = self.make_store()
        shared_key = f"conv-{uuid.uuid4().hex}"

        session_a = self.make_chat_session(store_a, conversation_key=shared_key)
        session_b = self.make_chat_session(store_b, conversation_key=shared_key)
        assert session_a.id != session_b.id

        service = ChatService(self._db)

        resolved_a = service._get_or_create_session(store_a.id, shared_key)
        assert resolved_a.id == session_a.id
        assert resolved_a.store_id == store_a.id
        assert resolved_a.id != session_b.id

        resolved_b = service._get_or_create_session(store_b.id, shared_key)
        assert resolved_b.id == session_b.id
        assert resolved_b.store_id == store_b.id

    def test_product_search_never_crosses_store_boundary(self):
        store_a = self.make_store()
        store_b = self.make_store()

        # Tokens unique per run so ILIKE cannot match leftovers of
        # earlier runs or other stores.
        token_a = f"aqubit{uuid.uuid4().hex[:8]}"
        token_b = f"zqflux{uuid.uuid4().hex[:8]}"

        product_a = self.make_product(store_a, f"Aqubit Sole {token_a}")
        product_b = self.make_product(store_b, f"Zqflux Runner {token_b}")

        service = ChatService(self._db)

        results_a = service._search_products(store_a.id, token_a, None)
        assert [p.id for p in results_a] == [product_a.id]
        assert all(p.store_id == store_a.id for p in results_a)
        assert product_b.id not in [p.id for p in results_a]

        results_b = service._search_products(store_b.id, token_b, None)
        assert [p.id for p in results_b] == [product_b.id]
        assert all(p.store_id == store_b.id for p in results_b)
        assert product_a.id not in [p.id for p in results_b]

        # Searching store A for a token that only exists in store B's
        # catalog must return nothing at all.
        assert service._search_products(store_a.id, token_b, None) == []


# ---------------------------------
# 4. Deterministic path — no LLM
# ---------------------------------

class TestDeterministicNoLLM(IsolatedStoreTestBase):
    """
    A pure greeting must be answered by the deterministic planner path:
    no LLM stack construction, no provider call, Bangla greeting, valid
    response envelope.

    Rate limiting lives in the HTTP router (Redis-backed) — these tests
    call ChatService.handle directly, so no Redis state is involved; the
    store is unique per run anyway.
    """

    GREETING = "hello"

    @pytest.mark.asyncio
    async def test_greeting_answered_without_llm_stack(self, monkeypatch):
        forbid_llm_stack(monkeypatch)

        store = self.make_store()
        conversation_id = f"conv-{uuid.uuid4().hex}"

        response = await ChatService(self._db).handle(
            store.id,
            ChatRequest(message=self.GREETING, conversation_id=conversation_id),
        )

        assert response["conversation_id"] == conversation_id
        assert "message" in response
        assert response["type"] == "general"
        assert "হ্যালো" in response["message"]
        assert response["products"] == []
        assert response["sources"] == []

    @pytest.mark.asyncio
    async def test_greeting_persists_user_and_assistant_messages(
        self, monkeypatch
    ):
        forbid_llm_stack(monkeypatch)

        store = self.make_store()
        conversation_id = f"conv-{uuid.uuid4().hex}"

        await ChatService(self._db).handle(
            store.id,
            ChatRequest(message=self.GREETING, conversation_id=conversation_id),
        )

        chat_session = (
            self._db.query(ChatSession)
            .filter(
                ChatSession.store_id == store.id,
                ChatSession.conversation_key == conversation_id,
            )
            .one()
        )

        messages = (
            self._db.query(ChatMessage)
            .filter(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

        assert [m.role for m in messages] == ["user", "assistant"]
        assert messages[0].content == self.GREETING
        assert "হ্যালো" in messages[1].content


# ---------------------------------
# 5. Budget exhausted
# ---------------------------------

class TestBudgetExhaustedMessage(IsolatedStoreTestBase):
    """
    A mixed (product + knowledge) query routes to the LLM-composed answer,
    but the atomic budget reservation must refuse when monthly_budget is
    0 (preflight cost > 0 can never fit). The caller gets the Bangla
    usage-limit message, the LLM stack is never built, and no usage
    record leaks.
    """

    MIXED_MESSAGE = "shoes return policy"

    @pytest.mark.asyncio
    async def test_budget_exhausted_returns_bangla_usage_message(
        self, monkeypatch
    ):
        forbid_llm_stack(monkeypatch)

        store = self.make_store(monthly_budget=0.0)
        conversation_id = f"conv-{uuid.uuid4().hex}"

        response = await ChatService(self._db).handle(
            store.id,
            ChatRequest(message=self.MIXED_MESSAGE, conversation_id=conversation_id),
        )

        assert response["type"] == "mixed"
        assert "usage" in response["message"]
        assert "দুঃখিত" in response["message"]

    @pytest.mark.asyncio
    async def test_budget_exhausted_leaves_no_usage_record(self, monkeypatch):
        forbid_llm_stack(monkeypatch)

        store = self.make_store(monthly_budget=0.0)

        response = await ChatService(self._db).handle(
            store.id,
            ChatRequest(
                message=self.MIXED_MESSAGE,
                conversation_id=f"conv-{uuid.uuid4().hex}",
            ),
        )

        assert "usage" in response["message"]

        reservations = (
            self._db.query(UsageRecord)
            .filter(UsageRecord.store_id == store.id)
            .all()
        )
        assert reservations == [], (
            "a rejected budget request must not persist any reservation"
        )

    @pytest.mark.asyncio
    async def test_budget_exhausted_still_persists_conversation(
        self, monkeypatch
    ):
        forbid_llm_stack(monkeypatch)

        store = self.make_store(monthly_budget=0.0)
        conversation_id = f"conv-{uuid.uuid4().hex}"

        await ChatService(self._db).handle(
            store.id,
            ChatRequest(message=self.MIXED_MESSAGE, conversation_id=conversation_id),
        )

        chat_session = (
            self._db.query(ChatSession)
            .filter(
                ChatSession.store_id == store.id,
                ChatSession.conversation_key == conversation_id,
            )
            .one()
        )

        roles = [
            m.role
            for m in self._db.query(ChatMessage)
            .filter(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        ]
        assert roles == ["user", "assistant"]


# ---------------------------------
# 6. SSRF guard (local checks only)
# ---------------------------------

# Every URL here is validated WITHOUT any network fetch: assert_safe_url
# raises either in the synchronous first pass (scheme / literal-host /
# local-name checks) or during localhost-only DNS resolution of numeric
# loopback encodings.
SSRF_BLOCKLIST_URLS = [
    "http://127.0.0.1/",
    "http://2130706433/",        # decimal encoding of 127.0.0.1
    "http://0x7f000001/",        # hex encoding of 127.0.0.1
    "http://169.254.169.254/",   # cloud metadata endpoint (link-local)
    "http://[::1]/",             # IPv6 loopback
    "file:///etc/passwd",        # non-http scheme
    "ftp://x/",                  # non-http scheme
    "http://localhost/",         # well-known local hostname
]

# URLs whose danger is caught by the SYNCHRONOUS first pass alone.
# (The decimal/hex literal encodings are only caught by the async
# assert_safe_url on modern Python — see the documented-gap test below.)
SYNC_FIRST_PASS_BLOCKED = [
    "http://127.0.0.1/",
    "http://169.254.169.254/",
    "http://[::1]/",
    "file:///etc/passwd",
    "ftp://x/",
    "http://localhost/",
]


class TestSSRFGuard:
    """SSRF validation in app/knowledge/crawler.py — no DB, no network."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", SSRF_BLOCKLIST_URLS)
    async def test_assert_safe_url_rejects_dangerous_urls(self, url):
        with pytest.raises(ValueError):
            await assert_safe_url(url)

    @pytest.mark.parametrize("url", SYNC_FIRST_PASS_BLOCKED)
    def test_is_private_host_flags_dangerous_urls(self, url):
        assert is_private_host(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://2130706433/",
            "http://0x7f000001/",
        ],
    )
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known gap: ipaddress.ip_address() rejects non-dotted and "
            "leading-zero IPv4 strings on Python >= 3.9.5, so "
            "_check_literal_host does not recognise decimal/hex loopback "
            "encodings despite its docstring. Exploitability is contained: "
            "assert_safe_url (the enforcement layer) still rejects them "
            "after DNS resolution."
        ),
    )
    def test_is_private_host_blocks_encoded_loopback(self, url):
        assert is_private_host(url) is True

    def test_is_private_host_allows_public_urls(self):
        # Pure parsing check — no DNS resolution happens here.
        assert is_private_host("https://example.com/products") is False
        assert is_private_host("https://sub.example.co.uk/") is False


# ---------------------------------
# 7. Knowledge isolation
# ---------------------------------

class TestKnowledgeIsolation(IsolatedStoreTestBase):
    """
    Keyword knowledge search (KnowledgeSearchEngine — the same entrypoint
    the /v1/knowledge/search endpoint uses) must be strictly store-scoped.

    Rows are inserted directly via the ORM (no crawler, no ingest, no
    sentence_transformers; the embedding column is Text because pgvector
    is disabled in this database).
    """

    def _make_knowledge(self, store: Store, token: str) -> KnowledgeChunk:
        page = KnowledgePage(
            id=str(uuid.uuid4()),
            store_id=store.id,
            url=f"https://example.test/{store.id}/{token}",
            title=f"Help center {token}",
            content=f"We ship worldwide. Reference {token} in this policy text.",
            content_hash=uuid.uuid4().hex,
            page_type="faq",
            status="active",
        )

        # Commit the parent FIRST: the ORM classes declare a bare
        # ForeignKey without relationship(), so the unit of work does not
        # order pending KnowledgePage inserts before KnowledgeChunk inserts
        # within one flush — emitting both together violates
        # knowledge_chunks_page_id_fkey.
        self._db.add(page)
        self._db.commit()

        chunk = KnowledgeChunk(
            id=str(uuid.uuid4()),
            store_id=store.id,
            page_id=page.id,
            chunk_index=0,
            content=f"Shipping policy details. Unique marker {token} for tests.",
        )
        self._db.add(chunk)
        self._db.commit()
        return chunk

    def test_keyword_search_never_crosses_store_boundary(self):
        store_a = self.make_store()
        store_b = self.make_store()

        token_a = f"kwmarkera{uuid.uuid4().hex[:8]}"
        token_b = f"kwmarkerb{uuid.uuid4().hex[:8]}"

        chunk_a = self._make_knowledge(store_a, token_a)
        chunk_b = self._make_knowledge(store_b, token_b)

        engine = KnowledgeSearchEngine(settings.database_url)

        # Store A asks for a word that only exists in store B's chunk.
        assert engine.search(store_id=store_a.id, query=token_b) == []

        # And vice versa.
        assert engine.search(store_id=store_b.id, query=token_a) == []

        # Each store finds its own chunk.
        hits_a = engine.search(store_id=store_a.id, query=token_a)
        assert len(hits_a) == 1
        assert hits_a[0].chunk_id == chunk_a.id
        assert token_a in hits_a[0].content

        hits_b = engine.search(store_id=store_b.id, query=token_b)
        assert len(hits_b) == 1
        assert hits_b[0].chunk_id == chunk_b.id

    def test_keyword_search_returns_result_shape(self):
        store_a = self.make_store()
        token_a = f"kwmarker{uuid.uuid4().hex[:8]}"
        self._make_knowledge(store_a, token_a)

        engine = KnowledgeSearchEngine(settings.database_url)
        hits = engine.search(store_id=store_a.id, query=token_a)

        assert len(hits) == 1
        hit = hits[0]
        assert hit.url.startswith("https://example.test/")
        assert hit.title is not None
        assert hit.score >= 0.0
        assert hasattr(hit, "page_id")

    def test_keyword_search_no_match_returns_empty(self):
        store_a = self.make_store()
        token_a = f"kwmarker{uuid.uuid4().hex[:8]}"
        self._make_knowledge(store_a, token_a)

        engine = KnowledgeSearchEngine(settings.database_url)

        assert (
            engine.search(
                store_id=store_a.id,
                query=f"nosuchtoken{uuid.uuid4().hex[:8]}",
            )
            == []
        )


# ---------------------------------
# 8. Auth divergence
# ---------------------------------

class TestAuthDivergence(IsolatedStoreTestBase):
    """
    authenticate_api_key (FastAPI dependency, called directly with a fake
    Header value) must enforce the pk_ prefix exactly like get_api_key:

    - missing header        -> 401 "API key required"
    - wrong prefix          -> 401
    - valid pk_ + hash hit  -> APIKey instance returned
    - revoked key           -> 401
    """

    @pytest.mark.asyncio
    async def test_missing_key_rejected_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_api_key(x_api_key=None, db=self._db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "API key required"

    @pytest.mark.asyncio
    async def test_wrong_prefix_rejected_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_api_key(x_api_key="sk_wrong", db=self._db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_pk_key_returns_api_key(self):
        store = self.make_store()

        raw_key = f"pk_live_{uuid.uuid4().hex}"
        api_key = APIKey(
            id=str(uuid.uuid4()),
            store_id=store.id,
            key_prefix=raw_key[:16],
            key_hash=hash_api_key(raw_key),
            name="pytest key",
            revoked_at=None,
        )
        self._db.add(api_key)
        self._db.commit()

        resolved = await authenticate_api_key(x_api_key=raw_key, db=self._db)

        assert isinstance(resolved, APIKey)
        assert resolved.id == api_key.id
        assert resolved.store_id == store.id
        assert resolved.key_hash == hash_api_key(raw_key)
        assert resolved.revoked_at is None

    @pytest.mark.asyncio
    async def test_revoked_key_rejected_401(self):
        store = self.make_store()

        raw_key = f"pk_live_{uuid.uuid4().hex}"
        self._db.add(
            APIKey(
                id=str(uuid.uuid4()),
                store_id=store.id,
                key_prefix=raw_key[:16],
                key_hash=hash_api_key(raw_key),
                name="revoked pytest key",
                revoked_at=datetime.utcnow(),
            )
        )
        self._db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await authenticate_api_key(x_api_key=raw_key, db=self._db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_but_wellformed_key_rejected_401(self):
        # Correct prefix, no matching hash in the DB.
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_api_key(
                x_api_key=f"pk_live_{uuid.uuid4().hex}", db=self._db
            )

        assert exc_info.value.status_code == 401
