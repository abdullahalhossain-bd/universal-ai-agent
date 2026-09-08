"""
Tests for the freshness-aware stock lookup wired into chat/service.py.

Uses an in-memory SQLite DB (Base.metadata.create_all works against it)
so this runs fast with no external Postgres/Redis dependency. These
tests exist to prove the wiring is real, not just import-clean:
StockService.check() must reflect actual row data and actual
DataSource.last_sync_at age, and ChatService's stock-question path
must surface a staleness caveat instead of presenting old numbers as
certain.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Store, Product, DataSource
from app.query_engine.tools.stock_tool import StockService


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _make_store(db):
    store = Store(name="Test Store")
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def _make_product(db, store, *, stock):
    product = Product(
        id="p1",
        store_id=store.id,
        name="Test Product",
        stock=stock,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def _make_datasource(db, store, *, last_sync_at):
    ds = DataSource(
        store_id=store.id,
        connector_type="postgresql",
        active=True,
        last_sync_at=last_sync_at,
    )
    db.add(ds)
    db.commit()
    return ds


def test_stock_fresh_in_stock(db_session):
    store = _make_store(db_session)
    product = _make_product(db_session, store, stock=5)
    _make_datasource(
        db_session,
        store,
        last_sync_at=datetime.now(timezone.utc),
    )

    result = StockService(db_session).check(store.id, product.id)

    assert result.source == "cache"
    assert result.in_stock is True
    assert result.stock == 5.0


def test_stock_stale_still_reports_last_known_value(db_session):
    store = _make_store(db_session)
    product = _make_product(db_session, store, stock=0)
    _make_datasource(
        db_session,
        store,
        last_sync_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    result = StockService(db_session).check(store.id, product.id)

    assert result.source == "cache_stale"
    assert result.in_stock is False
    # Never silently invents a number — the last known value is
    # returned along with the staleness signal, not a guess.
    assert result.stock == 0.0
    assert result.freshness_seconds > 300


def test_stock_unknown_product_never_fabricated(db_session):
    store = _make_store(db_session)

    result = StockService(db_session).check(store.id, "does-not-exist")

    assert result.source == "unavailable"
    assert result.stock is None
    assert result.in_stock is False


def test_datasource_service_create_rejects_private_connection_url(db_session):
    """
    Regression guard for the gap this pass fixed: /v1/datasources
    (and .create()/.update()) previously connected to whatever host
    was supplied with zero SSRF check. This proves the guard is
    actually invoked inside DataSourceService, not just importable.
    """
    from app.datasources.service import DataSourceService

    store = _make_store(db_session)
    service = DataSourceService(db_session)

    with pytest.raises(ConnectionError):
        service.create(
            store.id,
            name="evil",
            connector_type="postgresql",
            connection_url="postgresql://x@127.0.0.1:5432/db",
        )


def test_chat_service_stock_answer_includes_staleness_caveat(db_session):
    """
    This is the actual wiring test: ChatService._reference_message must
    call the real StockService (not read product.stock directly) and
    must surface a caveat when the underlying sync is stale, per the
    product requirement that the AI never present stale stock as
    certain.
    """
    from app.chat.service import ChatService

    store = _make_store(db_session)
    product = _make_product(db_session, store, stock=3)
    _make_datasource(
        db_session,
        store,
        last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )

    service = ChatService(db_session)
    reply = service._reference_message(
        "stock আছে?",
        [product],
    )

    assert "৩টি" in reply or "3টি" in reply or "3" in reply
    assert "মিনিট আগে" in reply, (
        "expected a staleness caveat in the reply for a 45-minute-old "
        f"sync, got: {reply!r}"
    )


def test_chat_service_stock_message_shared_by_fresh_search_path(db_session):
    """
    A fresh single-product search that is also a stock question
    ("... stock আছে?") must go through the same StockService-backed
    `_stock_message()` as the reference ("এটার") path — not just read
    the raw `product.stock` column via `_serialize_products` /
    `_product_message`, which would silently skip the staleness
    caveat for the very first turn of a conversation.
    """
    from app.chat.service import ChatService

    store = _make_store(db_session)
    product = _make_product(db_session, store, stock=3)
    _make_datasource(
        db_session,
        store,
        last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )

    service = ChatService(db_session)

    # Exercise the extracted helper directly against a *freshly
    # fetched* product object, exactly as the fresh-search branch in
    # handle() would call it.
    reply = service._stock_message(product)

    assert "৩টি" in reply or "3টি" in reply or "3" in reply
    assert "মিনিট আগে" in reply, (
        "expected the same staleness caveat as the reference path, "
        f"got: {reply!r}"
    )
