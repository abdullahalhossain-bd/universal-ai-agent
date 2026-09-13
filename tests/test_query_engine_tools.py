"""
Tests for app/query_engine — this subsystem is not on the live chat
path yet (see app/ARCHITECTURE_CLEANUP.md), but its tools should
actually work end-to-end so whoever wires it in next isn't met with
silent NotImplementedError stubs.

`ImageAnalysisTool` used to be the one deliberate exception (see git
history) — it is now fully wired to a real `ChatImage` table and
`VisionService`, so its tests below exercise the real thing instead
of asserting it still refuses to run.
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
from app.query_engine.plan import QueryPlan, PlanStep
from app.query_engine.executor import PlanExecutor
from app.query_engine.tools.product_search import ProductSearchTool
from app.query_engine.tools.knowledge_search import KnowledgeSearchTool
from app.query_engine.tools.image_analysis import ImageAnalysisTool
from app.knowledge.search_models import KnowledgeSearchResult


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
def store(db_session):
    s = Store(
        id=str(uuid.uuid4()),
        name="Test Store",
        plan="starter",
        monthly_budget=100.0,
        status="active",
    )
    db_session.add(s)
    db_session.commit()
    return s


def _make_product(store_id, product_id, name, price=100.0, stock=5):
    return Product(
        id=product_id,
        store_id=store_id,
        name=name,
        price=price,
        stock=stock,
    )


class _FakeKnowledgeSearchEngine:
    """Stand-in for KnowledgeSearchEngine — avoids needing real
    Postgres full-text search (ts_rank_cd/ILIKE) in tests."""

    def __init__(self, canned_results):
        self.canned_results = canned_results
        self.last_call = None

    def search(self, *, store_id, query, limit=5):
        self.last_call = {
            "store_id": store_id,
            "query": query,
            "limit": limit,
        }
        return self.canned_results


# ---------------------------------------------------------------------------
# ProductSearchTool
# ---------------------------------------------------------------------------


async def _run(coro):
    return await coro


def test_product_search_tool_requires_bind_db():
    import asyncio

    tool = ProductSearchTool()
    result = asyncio.run(tool.execute(tenant_id="store-1"))
    assert "error" in result


def test_product_search_tool_scopes_to_store(db_session, store):
    import asyncio

    other_store_id = str(uuid.uuid4())
    db_session.add_all(
        [
            _make_product(store.id, "P1", "Blue Cotton Shirt"),
            _make_product(other_store_id, "P2", "Blue Cotton Shirt"),
        ]
    )
    db_session.commit()

    tool = ProductSearchTool(db=db_session)
    results = asyncio.run(
        tool.execute(tenant_id=store.id, filters={}, query=None)
    )

    assert len(results) == 1
    assert results[0]["id"] == "P1"


def test_product_search_tool_applies_price_filter(db_session, store):
    import asyncio

    db_session.add_all(
        [
            _make_product(store.id, "CHEAP", "Item A", price=50.0),
            _make_product(store.id, "EXPENSIVE", "Item B", price=500.0),
        ]
    )
    db_session.commit()

    tool = ProductSearchTool(db=db_session)
    results = asyncio.run(
        tool.execute(
            tenant_id=store.id,
            filters={"max_price": 100.0},
        )
    )

    ids = {r["id"] for r in results}
    assert ids == {"CHEAP"}


def test_product_search_tool_color_filter_uses_synonyms(db_session, store):
    import asyncio

    db_session.add_all(
        [
            _make_product(store.id, "BLACK-1", "Black Running Shoe"),
            _make_product(store.id, "WHITE-1", "White Running Shoe"),
        ]
    )
    db_session.commit()

    tool = ProductSearchTool(db=db_session)
    results = asyncio.run(
        tool.execute(
            tenant_id=store.id,
            filters={"color": "কালো"},  # Bangla for "black"
        )
    )

    ids = {r["id"] for r in results}
    assert ids == {"BLACK-1"}


# ---------------------------------------------------------------------------
# KnowledgeSearchTool
# ---------------------------------------------------------------------------


def test_knowledge_search_tool_requires_query():
    import asyncio

    tool = KnowledgeSearchTool(search_engine=_FakeKnowledgeSearchEngine([]))
    result = asyncio.run(tool.execute(tenant_id="store-1", query=None))
    assert "error" in result


def test_knowledge_search_tool_maps_top_result(store):
    import asyncio

    fake = _FakeKnowledgeSearchEngine(
        [
            KnowledgeSearchResult(
                chunk_id="c1",
                page_id="p1",
                url="https://example.com/returns",
                title="Return Policy",
                content="You can return items within 7 days.",
                score=0.9,
            )
        ]
    )
    tool = KnowledgeSearchTool(search_engine=fake)

    result = asyncio.run(
        tool.execute(tenant_id=store.id, query="what is your return policy")
    )

    assert result["answer"] == "You can return items within 7 days."
    assert result["source"]["title"] == "Return Policy"
    assert result["source"]["url"] == "https://example.com/returns"
    assert len(result["results"]) == 1

    # Confirms the store never leaks into another store's search.
    assert fake.last_call["store_id"] == store.id


def test_knowledge_search_tool_handles_no_results():
    import asyncio

    tool = KnowledgeSearchTool(search_engine=_FakeKnowledgeSearchEngine([]))
    result = asyncio.run(
        tool.execute(tenant_id="store-1", query="unanswerable question")
    )
    assert result == {"answer": None, "source": None, "results": []}


# ---------------------------------------------------------------------------
# ImageAnalysisTool
# ---------------------------------------------------------------------------


def test_image_analysis_tool_requires_db_session():
    import asyncio

    tool = ImageAnalysisTool()

    result = asyncio.run(
        tool.execute(tenant_id="store-1", filters={"image_id": "img-1"})
    )

    assert "bind_db" in result["error"]


def test_image_analysis_tool_requires_image_id(db_session):
    import asyncio

    tool = ImageAnalysisTool(db=db_session)

    result = asyncio.run(tool.execute(tenant_id="store-1", filters={}))

    assert "image_id" in result["error"]


def test_image_analysis_tool_reports_missing_image(db_session, store):
    import asyncio

    tool = ImageAnalysisTool(db=db_session)

    result = asyncio.run(
        tool.execute(
            tenant_id=store.id,
            filters={"image_id": "does-not-exist"},
        )
    )

    assert "not found" in result["error"]


def test_image_analysis_tool_matches_products_from_vision_attributes(
    db_session, store, monkeypatch
):
    """
    End-to-end with a real persisted ChatImage + real ProductMatcher,
    but a fake VisionService (no network / no Groq key needed) —
    this is the seam that stands in for the actual vision-model call
    everywhere else in the test suite avoids real network calls.
    """
    import asyncio
    from app.images.repository import ImageRepository
    from app.query_engine.tools import image_analysis as image_analysis_module

    db_session.add(_make_product(store.id, "P1", "Red Leather Handbag"))
    db_session.add(_make_product(store.id, "P2", "Blue Cotton T-Shirt"))
    db_session.commit()

    image_record = ImageRepository(db_session).create(
        store_id=store.id,
        storage_key=f"{store.id}/abc.jpg",
        mime_type="image/jpeg",
        size=1234,
        image_hash="abc123",
    )

    class _FakeVisionService:
        def __init__(self, db, usage_repo=None):
            pass

        async def analyze(self, *, store, image_record, task, question=None):
            return {
                "description": "A red leather handbag",
                "category": "handbag",
                "colors": ["red"],
                "keywords": ["leather", "handbag"],
                "brand": None,
            }

    monkeypatch.setattr(
        image_analysis_module, "VisionService", _FakeVisionService
    )

    tool = ImageAnalysisTool(db=db_session)

    result = asyncio.run(
        tool.execute(
            tenant_id=store.id,
            filters={"image_id": image_record.id},
        )
    )

    assert "error" not in result
    assert result["analysis"]["category"] == "handbag"
    product_ids = {p["id"] for p in result["products"]}
    assert "P1" in product_ids
    assert "P2" not in product_ids


# ---------------------------------------------------------------------------
# PlanExecutor — end-to-end wiring
# ---------------------------------------------------------------------------


def test_plan_executor_binds_db_and_runs_product_search(db_session, store):
    import asyncio

    db_session.add(_make_product(store.id, "P1", "Red Bag", price=80.0))
    db_session.commit()

    plan = QueryPlan(
        intent="product_search",
        steps=[
            PlanStep(tool="product_search", filters={"max_price": 100.0})
        ],
    )

    executor = PlanExecutor()
    results = asyncio.run(
        executor.run(tenant_id=store.id, plan=plan, db=db_session)
    )

    assert "error" not in results["product_search"]
    assert results["product_search"][0]["id"] == "P1"


def test_plan_executor_surfaces_unknown_tool():
    import asyncio

    plan = QueryPlan(
        intent="unknown",
        steps=[PlanStep(tool="does_not_exist")],
    )

    executor = PlanExecutor()
    results = asyncio.run(
        executor.run(tenant_id="store-1", plan=plan, db=None)
    )

    assert results["does_not_exist"] == {"error": "unknown tool"}


def test_plan_executor_turns_image_analysis_failure_into_error_dict():
    """
    No `db` bound (executor called with db=None) and no `image_id`
    in filters — the tool must fail gracefully as an `{"error": ...}`
    result, same contract as ProductSearchTool with no db, not a
    raised exception that would blow up the whole plan.
    """
    import asyncio

    plan = QueryPlan(
        intent="image_search",
        steps=[PlanStep(tool="image_analysis")],
    )

    executor = PlanExecutor()
    results = asyncio.run(
        executor.run(tenant_id="store-1", plan=plan, db=None)
    )

    assert "error" in results["image_analysis"]