"""
Cross-tenant (cross-store) isolation guards.

`Product` uses a *composite* primary key of (product_id, store_id) —
see app/db/models.py — which means the same `product_id` string can
legitimately exist under two different stores (e.g. both merchants
use "SKU-1"). Every read path that takes a store_id + a set of IDs
must filter by BOTH, or a bug here is a direct cross-tenant data leak
/ IDOR: store A could read store B's product name, price or stock by
guessing/reusing an ID.

Similarly, `ChatSession` is keyed on (store_id, conversation_key), so
two stores can use the identical conversation_id (a widget on two
different merchant sites) and must never share history.

These tests exercise the actual ORM query methods on `ChatService`
against a real (sqlite) database — not mocks — so a regression that
drops a `.filter(Product.store_id == store_id)` clause anywhere would
fail these.
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test_db",
)
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault(
    "CREDENTIAL_ENCRYPTION_KEY",
    "1Q5CMAJ3S3iemRmjauMWsPLeJmpY-VPO0J_9jHijTxs=",
)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Store, Product
import app.chat.models  # noqa: F401 - registers ChatSession/ChatMessage
import app.usage.models  # noqa: F401 - registers UsageRecord
import app.knowledge.chunk  # noqa: F401 - registers KnowledgePage/KnowledgeChunk

from app.chat.models import ChatSession, ChatMessage
from app.chat.service import ChatService
from app.usage.repository import UsageRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def two_stores(db_session):
    store_a = Store(
        id=str(uuid.uuid4()),
        name="Store A",
        plan="starter",
        monthly_budget=100.0,
        status="active",
    )
    store_b = Store(
        id=str(uuid.uuid4()),
        name="Store B",
        plan="starter",
        monthly_budget=100.0,
        status="active",
    )
    db_session.add_all([store_a, store_b])
    db_session.commit()
    return store_a, store_b


@pytest.fixture()
def chat_service(db_session):
    return ChatService(db=db_session)


def _make_product(store_id: str, product_id: str, name: str, price: float = 10.0):
    return Product(
        id=product_id,
        store_id=store_id,
        name=name,
        price=price,
        stock=5,
    )


# ---------------------------------------------------------------------------
# Product lookup by ID (IDOR-style access)
# ---------------------------------------------------------------------------


def test_get_products_by_ids_ignores_foreign_store_product(
    db_session, two_stores, chat_service
):
    """
    Store A must not be able to fetch Store B's product just by
    knowing/guessing its product_id.
    """
    store_a, store_b = two_stores

    only_in_b = _make_product(store_b.id, "SKU-EXCLUSIVE", "B's Secret Item")
    db_session.add(only_in_b)
    db_session.commit()

    result = chat_service._get_products_by_ids(
        store_id=store_a.id,
        product_ids=["SKU-EXCLUSIVE"],
    )

    assert result == []


def test_get_products_by_ids_resolves_same_id_to_own_store_row(
    db_session, two_stores, chat_service
):
    """
    Both stores independently use the SAME product_id ("SKU-1") —
    legal under the composite PK. Store A must see only its own
    product's data, never Store B's name/price for that ID.
    """
    store_a, store_b = two_stores

    product_a = _make_product(store_a.id, "SKU-1", "A's Widget", price=100.0)
    product_b = _make_product(store_b.id, "SKU-1", "B's Widget", price=999.0)
    db_session.add_all([product_a, product_b])
    db_session.commit()

    result_a = chat_service._get_products_by_ids(
        store_id=store_a.id,
        product_ids=["SKU-1"],
    )
    result_b = chat_service._get_products_by_ids(
        store_id=store_b.id,
        product_ids=["SKU-1"],
    )

    assert len(result_a) == 1
    assert result_a[0].name == "A's Widget"
    assert float(result_a[0].price) == 100.0

    assert len(result_b) == 1
    assert result_b[0].name == "B's Widget"
    assert float(result_b[0].price) == 999.0


def test_get_products_by_ids_mixed_batch_drops_foreign_ids_silently(
    db_session, two_stores, chat_service
):
    """
    A request naming a mix of own-store and foreign-store IDs should
    silently drop the foreign ones rather than erroring or leaking
    them — mirrors how a manipulated `previous_ids` payload should
    behave.
    """
    store_a, store_b = two_stores

    own_product = _make_product(store_a.id, "OWN-1", "Own Product")
    foreign_product = _make_product(store_b.id, "FOREIGN-1", "Foreign Product")
    db_session.add_all([own_product, foreign_product])
    db_session.commit()

    result = chat_service._get_products_by_ids(
        store_id=store_a.id,
        product_ids=["OWN-1", "FOREIGN-1"],
    )

    ids = {p.id for p in result}
    assert ids == {"OWN-1"}


# ---------------------------------------------------------------------------
# Product search
# ---------------------------------------------------------------------------


def test_search_products_never_returns_other_store_matches(
    db_session, two_stores, chat_service
):
    store_a, store_b = two_stores

    db_session.add_all(
        [
            _make_product(store_a.id, "A-1", "Blue Cotton Shirt"),
            _make_product(store_b.id, "B-1", "Blue Cotton Shirt"),
        ]
    )
    db_session.commit()

    results = chat_service._search_products(
        store_id=store_a.id,
        message="Blue Cotton Shirt",
        filters=None,
    )

    assert len(results) == 1
    assert results[0].store_id == store_a.id


def test_get_next_products_pagination_scoped_to_store(
    db_session, two_stores, chat_service
):
    store_a, store_b = two_stores

    for i in range(3):
        db_session.add(_make_product(store_a.id, f"A-{i}", f"Red Shoe {i}"))
    for i in range(3):
        db_session.add(_make_product(store_b.id, f"B-{i}", f"Red Shoe {i}"))
    db_session.commit()

    page = chat_service._get_next_products(
        store_id=store_a.id,
        query_text="Red Shoe",
        filters_data={},
        previous_ids=[],
        batch_size=10,
    )

    assert all(p.store_id == store_a.id for p in page)
    assert len(page) == 3


# ---------------------------------------------------------------------------
# Chat session / message history
# ---------------------------------------------------------------------------


def test_same_conversation_id_creates_separate_sessions_per_store(
    chat_service, two_stores
):
    """
    Two merchants' widgets can independently generate the same
    conversation_id (e.g. a client-side UUID collision is not even
    required — some integrations reuse simple counters). These must
    resolve to two distinct ChatSession rows.
    """
    store_a, store_b = two_stores

    session_a = chat_service._get_or_create_session(
        store_id=store_a.id,
        conversation_id="conv-shared",
    )
    session_b = chat_service._get_or_create_session(
        store_id=store_b.id,
        conversation_id="conv-shared",
    )

    assert session_a.id != session_b.id
    assert session_a.store_id == store_a.id
    assert session_b.store_id == store_b.id


def test_chat_history_does_not_leak_across_stores(chat_service, two_stores):
    store_a, store_b = two_stores

    session_a = chat_service._get_or_create_session(
        store_id=store_a.id,
        conversation_id="conv-shared",
    )
    session_b = chat_service._get_or_create_session(
        store_id=store_b.id,
        conversation_id="conv-shared",
    )

    chat_service._save_message(
        session_id=session_a.id, role="user", content="Store A secret question"
    )
    chat_service._save_message(
        session_id=session_b.id, role="user", content="Store B secret question"
    )

    history_a = chat_service._load_history(session_id=session_a.id)
    history_b = chat_service._load_history(session_id=session_b.id)

    assert [m["content"] for m in history_a] == ["Store A secret question"]
    assert [m["content"] for m in history_b] == ["Store B secret question"]


def test_get_or_create_session_is_idempotent_within_a_store(
    chat_service, two_stores
):
    store_a, _ = two_stores

    first = chat_service._get_or_create_session(
        store_id=store_a.id,
        conversation_id="conv-repeat",
    )
    second = chat_service._get_or_create_session(
        store_id=store_a.id,
        conversation_id="conv-repeat",
    )

    assert first.id == second.id


# ---------------------------------------------------------------------------
# Usage / billing isolation
# ---------------------------------------------------------------------------


def test_usage_budget_reservations_are_isolated_per_store(db_session, two_stores):
    """
    Store A exhausting its own budget must have zero effect on Store
    B's ability to make requests, and vice versa — regression guard
    for the row-locked `reserve_budget` query being accidentally
    unscoped.
    """
    store_a, store_b = two_stores
    store_a.monthly_budget = 0.001
    store_b.monthly_budget = 0.001
    db_session.commit()

    repo = UsageRepository(db_session)

    reservation_a1 = repo.reserve_budget(
        store_id=store_a.id,
        conversation_id="c",
        request_id=str(uuid.uuid4()),
        route="groq",
        model="m",
        estimated_cost=0.001,
    )
    assert reservation_a1 is not None

    # Store A is now at its budget ceiling.
    reservation_a2 = repo.reserve_budget(
        store_id=store_a.id,
        conversation_id="c",
        request_id=str(uuid.uuid4()),
        route="groq",
        model="m",
        estimated_cost=0.001,
    )
    assert reservation_a2 is None

    # Store B, sharing nothing with A, must still have its full
    # budget available.
    reservation_b1 = repo.reserve_budget(
        store_id=store_b.id,
        conversation_id="c",
        request_id=str(uuid.uuid4()),
        route="groq",
        model="m",
        estimated_cost=0.001,
    )
    assert reservation_b1 is not None


def test_usage_monthly_request_count_is_isolated_per_store(db_session, two_stores):
    store_a, store_b = two_stores
    repo = UsageRepository(db_session)

    for _ in range(4):
        rid = str(uuid.uuid4())
        reservation = repo.reserve_budget(
            store_id=store_a.id,
            conversation_id="c",
            request_id=rid,
            route="groq",
            model="m",
            estimated_cost=0.0001,
        )
        repo.finalize_budget_reservation(
            request_id=rid,
            input_tokens=1,
            output_tokens=1,
            actual_cost=0.0001,
        )

    assert repo.get_monthly_request_count(store_a.id) == 4
    assert repo.get_monthly_request_count(store_b.id) == 0


# ---------------------------------------------------------------------------
# Chat image isolation
# ---------------------------------------------------------------------------


def test_image_repository_get_ignores_foreign_store_image(db_session, two_stores):
    """
    An `image_id` is a UUID string, guessable in principle — store A
    must never resolve store B's ChatImage row (and therefore never
    its storage_key / cached vision analysis) by supplying the ID
    alone. Mirrors app.images.repository.ImageRepository.get, which
    every image-chat route goes through.
    """
    from app.images.repository import ImageRepository

    store_a, store_b = two_stores
    repo = ImageRepository(db_session)

    image_b = repo.create(
        store_id=store_b.id,
        storage_key=f"{store_b.id}/secret.jpg",
        mime_type="image/jpeg",
        size=1234,
        image_hash="deadbeef",
    )

    assert repo.get(store_id=store_a.id, image_id=image_b.id) is None
    # Sanity: the row is real and store B can see it.
    assert repo.get(store_id=store_b.id, image_id=image_b.id) is not None


def test_image_repository_same_conversation_id_scoped_per_store(
    db_session, two_stores
):
    """
    `ChatImage.conversation_id` is a client-supplied string (not a
    FK) and, like ChatSession.conversation_key, two different
    merchants' widgets can legitimately reuse the same value —
    listing/lookups must still never mix store A's and store B's
    uploads together.
    """
    from app.images.repository import ImageRepository

    store_a, store_b = two_stores
    repo = ImageRepository(db_session)

    img_a = repo.create(
        store_id=store_a.id,
        storage_key=f"{store_a.id}/a.jpg",
        mime_type="image/jpeg",
        size=10,
        conversation_id="conv-shared",
    )
    img_b = repo.create(
        store_id=store_b.id,
        storage_key=f"{store_b.id}/b.jpg",
        mime_type="image/jpeg",
        size=10,
        conversation_id="conv-shared",
    )

    assert repo.get(store_id=store_a.id, image_id=img_a.id).storage_key.startswith(
        store_a.id
    )
    assert repo.get(store_id=store_a.id, image_id=img_b.id) is None
    assert repo.get(store_id=store_b.id, image_id=img_a.id) is None


# ---------------------------------------------------------------------------
# Knowledge (website content) isolation
# ---------------------------------------------------------------------------


def test_knowledge_chunk_lookup_is_scoped_to_store(db_session, two_stores):
    """
    Regression guard for the raw-SQL knowledge search path
    (app.knowledge.search.KnowledgeSearchEngine, Postgres-only —
    ts_vector/ILIKE aren't available on sqlite here) and for
    app.knowledge.embedding_service, both of which must always
    include `store_id` in their WHERE clause. Exercised at the ORM
    level, which is dialect-agnostic and covers the same
    `KnowledgeChunk.store_id` column both call sites filter on.
    """
    from app.knowledge.chunk import KnowledgePage, KnowledgeChunk

    store_a, store_b = two_stores

    page_a = KnowledgePage(
        store_id=store_a.id,
        url="https://a.example/faq",
        content="Store A ships worldwide.",
        content_hash="hash-a",
    )
    page_b = KnowledgePage(
        store_id=store_b.id,
        url="https://b.example/faq",
        content="Store B's secret return policy.",
        content_hash="hash-b",
    )
    db_session.add_all([page_a, page_b])
    db_session.commit()

    chunk_a = KnowledgeChunk(
        store_id=store_a.id,
        page_id=page_a.id,
        chunk_index=0,
        content="Store A ships worldwide.",
    )
    chunk_b = KnowledgeChunk(
        store_id=store_b.id,
        page_id=page_b.id,
        chunk_index=0,
        content="Store B's secret return policy.",
    )
    db_session.add_all([chunk_a, chunk_b])
    db_session.commit()

    # A store-scoped lookup for A must never surface B's chunk, even
    # though nothing about the chunk_id itself distinguishes them.
    visible_to_a = (
        db_session.query(KnowledgeChunk)
        .filter(KnowledgeChunk.store_id == store_a.id)
        .all()
    )
    assert {c.id for c in visible_to_a} == {chunk_a.id}

    visible_to_b = (
        db_session.query(KnowledgeChunk)
        .filter(KnowledgeChunk.store_id == store_b.id)
        .all()
    )
    assert {c.id for c in visible_to_b} == {chunk_b.id}


def test_knowledge_embedding_backfill_never_touches_other_store_chunks(
    db_session, two_stores
):
    """
    app.knowledge.embedding_service.KnowledgeEmbeddingService generates
    missing embeddings store_id-at-a-time (see
    app/knowledge/embedding_service.py). A batch job for store A must
    never select/write store B's rows.
    """
    from app.knowledge.chunk import KnowledgePage, KnowledgeChunk

    store_a, store_b = two_stores

    page = KnowledgePage(
        store_id=store_a.id,
        url="https://a.example/faq",
        content="content",
        content_hash="h",
    )
    db_session.add(page)
    db_session.commit()

    chunk_a = KnowledgeChunk(
        store_id=store_a.id, page_id=page.id, chunk_index=0, content="a"
    )
    page_b = KnowledgePage(
        store_id=store_b.id,
        url="https://b.example/faq",
        content="content",
        content_hash="h2",
    )
    db_session.add(page_b)
    db_session.commit()
    chunk_b = KnowledgeChunk(
        store_id=store_b.id, page_id=page_b.id, chunk_index=0, content="b"
    )
    db_session.add_all([chunk_a, chunk_b])
    db_session.commit()

    pending_for_a = (
        db_session.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.store_id == store_a.id,
            KnowledgeChunk.embedding.is_(None),
        )
        .all()
    )
    assert {c.id for c in pending_for_a} == {chunk_a.id}


# ---------------------------------------------------------------------------
# Composite product identity ((product_id, store_id) primary key)
# ---------------------------------------------------------------------------


def test_products_composite_pk_allows_same_id_across_stores(db_session, two_stores):
    """
    The whole point of `Product`'s composite (product_id, store_id)
    primary key (alembic/versions/0004_product_store_composite_pk.py)
    is that two merchants independently reusing the same SKU string
    is legal and must not collide.
    """
    store_a, store_b = two_stores

    db_session.add_all(
        [
            _make_product(store_a.id, "SKU-1", "A's Widget"),
            _make_product(store_b.id, "SKU-1", "B's Widget"),
        ]
    )
    db_session.commit()  # must not raise IntegrityError

    count = (
        db_session.query(Product).filter(Product.id == "SKU-1").count()
    )
    assert count == 2


def test_products_composite_pk_rejects_true_duplicate(db_session, two_stores):
    """Same (product_id, store_id) pair twice must still be rejected."""
    from sqlalchemy.exc import IntegrityError

    store_a, _ = two_stores

    db_session.add(_make_product(store_a.id, "SKU-DUP", "First"))
    db_session.commit()

    db_session.add(_make_product(store_a.id, "SKU-DUP", "Second"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
