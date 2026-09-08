"""
Task 3-b — Budget / rate-limit / security integration tests.

Test classes
------------
1. TestBudgetReservationLifecycle  real-DB reservation create / finalize / fail
2. TestBudgetExpiry                stale reservations expire and stop counting
3. TestBudgetIdempotency           request_id idempotency for reserve + record
4. TestBudgetOverspendRejected     reservations beyond budget are rejected
5. TestBudgetLockSerialization     concurrent reserve_budget serialized by FOR UPDATE
6. TestRateLimiterAtomic           real-Redis atomic INCR/EXPIRE (Lua) limiter
7. TestClientIPResolution          X-Forwarded-For anti-spoofing rules
8. TestAuthPrefixEnforcement       unified pk_ prefix rules across both auth deps

Hygiene rules honored by this module
------------------------------------
- Every Store row is created with a uuid-suffixed unique name; teardown deletes
  child rows (usage_records, api_keys) before deleting the store row itself.
- No DDL, no alembic, no cross-store data access (all repository expiry calls
  are store-scoped).
- Redis keys are namespaced ``test_3b:*`` and scan-deleted in fixture teardown.
- Each async test gets a fresh Redis client (pytest-asyncio gives each test its
  own event loop; the app-level pooled client must not be reused across loops).
"""

import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
import redis.asyncio as redis_async
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.auth.api_key import get_api_key
from app.auth.dependency import authenticate_api_key
from app.core import rate_limit
from app.core.config import settings
from app.core.security import (
    get_trusted_proxies,
    hash_api_key,
    resolve_client_ip,
)
from app.db.database import SessionLocal
from app.db.models import APIKey, Store
from app.usage.models import UsageRecord
from app.usage.repository import UsageRepository

from tests.markers import (
    requires_postgres,
    requires_redis,
    skip_unless_postgres,
    skip_unless_redis,
)


# ---------------------------------
# Helpers
# ---------------------------------


def _uid() -> str:
    """Short unique suffix so re-runs never collide with leftover rows."""
    return uuid.uuid4().hex[:12]


def _request_id() -> str:
    return f"test_3b_{uuid.uuid4().hex[:12]}"


def _cleanup_store(store_id: str) -> None:
    """
    Delete every row created for this store, children first.

    Only tables this test module writes (usage_records, api_keys) are
    touched; the delete is scoped by store_id so no other store's data
    can be affected.
    """
    with SessionLocal() as session:
        session.query(UsageRecord).filter(
            UsageRecord.store_id == store_id
        ).delete(synchronize_session=False)
        session.query(APIKey).filter(
            APIKey.store_id == store_id
        ).delete(synchronize_session=False)
        session.query(Store).filter(
            Store.id == store_id
        ).delete(synchronize_session=False)
        session.commit()


def _make_store(monthly_budget: Decimal | float) -> Store:
    """Create a committed Store row with a unique uuid-suffixed name."""
    with SessionLocal() as session:
        store = Store(
            name=f"test_3b_{_uid()}",
            monthly_budget=monthly_budget,
            status="active",
        )
        session.add(store)
        session.commit()
        session.refresh(store)
        # Detach a plain copy so the object survives session close.
        detached = Store(
            id=store.id,
            name=store.name,
            monthly_budget=store.monthly_budget,
            plan=store.plan,
            status=store.status,
        )
        return detached


# ---------------------------------
# Shared fixtures
# ---------------------------------


@pytest.fixture
def db_session():
    # Recent pytest (see docs/deprecations.html#applying-a-mark-to-a-fixture-
    # function) refuses to collect a fixture decorated with a mark like
    # `@requires_postgres` at all -- marks only apply to test *functions*.
    # The runtime skip below (skip_unless_postgres) is what actually does
    # the work; every test that uses this fixture is itself still marked
    # `@requires_postgres` so `pytest -m` filtering keeps working too.
    skip_unless_postgres()  # runtime re-check (auth / IPv6 drift)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()  # implicit rollback of anything uncommitted


@pytest.fixture
def budget_store():
    """Store with a tiny 0.001 monthly budget, cleaned up on teardown."""
    skip_unless_postgres()
    store = _make_store(Decimal("0.001"))
    store_id = store.id
    try:
        yield store
    finally:
        _cleanup_store(store_id)


# =================================================================
# 1. Reservation lifecycle
# =================================================================


@requires_postgres
class TestBudgetReservationLifecycle:
    """reserve_budget -> finalize / fail, against the real database."""

    def test_reserve_creates_reserved_row_with_future_expiry(
        self, budget_store
    ):
        rid = _request_id()
        with SessionLocal() as session:
            repo = UsageRepository(session)
            before = datetime.utcnow()

            rec = repo.reserve_budget(
                store_id=budget_store.id,
                conversation_id=f"conv_{_uid()}",
                request_id=rid,
                route="chat",
                model="test-model",
                estimated_cost=0.001,
            )

            after = datetime.utcnow()

            assert rec is not None
            assert rec.id is not None
            assert rec.request_id == rid
            assert rec.store_id == budget_store.id
            assert rec.status == "reserved"
            assert rec.input_tokens == 0
            assert rec.output_tokens == 0
            assert float(rec.estimated_cost) == pytest.approx(0.001)
            assert rec.expires_at is not None
            # TTL is 300s by default: expiry strictly in the future.
            assert rec.expires_at > before
            assert rec.expires_at <= after + timedelta(seconds=301)

    def test_finalize_completes_with_actual_tokens_and_cost(
        self, budget_store
    ):
        rid = _request_id()
        with SessionLocal() as session:
            repo = UsageRepository(session)

            rec = repo.reserve_budget(
                store_id=budget_store.id,
                conversation_id=f"conv_{_uid()}",
                request_id=rid,
                route="chat",
                model="test-model",
                estimated_cost=0.001,
            )
            assert rec is not None
            assert rec.status == "reserved"

            done = repo.finalize_budget_reservation(
                request_id=rid,
                input_tokens=120,
                output_tokens=80,
                actual_cost=0.0004,
                latency_ms=250,
                cache_hit=True,
            )

            assert done is not None
            assert done.id == rec.id
            assert done.status == "completed"
            assert done.input_tokens == 120
            assert done.output_tokens == 80
            assert float(done.estimated_cost) == pytest.approx(0.0004)
            assert done.latency_ms == 250
            assert done.cache_hit is True
            assert done.expires_at is None

            # Completed usage now counts toward the monthly bucket...
            assert repo.get_monthly_usage(budget_store.id) == pytest.approx(
                0.0004
            )
            # ...and nothing is left actively reserved.
            assert repo.get_active_reserved_usage(
                budget_store.id
            ) == pytest.approx(0.0)

    def test_fail_zeroes_cost_and_releases_budget(self, budget_store):
        rid = _request_id()
        with SessionLocal() as session:
            repo = UsageRepository(session)

            rec = repo.reserve_budget(
                store_id=budget_store.id,
                conversation_id=f"conv_{_uid()}",
                request_id=rid,
                route="chat",
                model="test-model",
                estimated_cost=0.001,
            )
            assert rec is not None
            assert rec.status == "reserved"

            failed = repo.fail_budget_reservation(request_id=rid)

            assert failed is not None
            assert failed.id == rec.id
            assert failed.status == "failed"
            assert float(failed.estimated_cost) == 0.0
            assert failed.input_tokens == 0
            assert failed.output_tokens == 0
            assert failed.expires_at is None

            # A failed reservation must not consume any budget.
            assert repo.get_monthly_usage(budget_store.id) == pytest.approx(
                0.0
            )
            assert repo.get_monthly_committed_usage(
                budget_store.id
            ) == pytest.approx(0.0)

        # Budget was fully released: a fresh full-budget reservation fits.
        with SessionLocal() as session:
            repo = UsageRepository(session)
            retry = repo.reserve_budget(
                store_id=budget_store.id,
                conversation_id=f"conv_{_uid()}",
                request_id=_request_id(),
                route="chat",
                model="test-model",
                estimated_cost=0.001,
            )
            assert retry is not None
            assert retry.status == "reserved"


# =================================================================
# 2. Reservation expiry
# =================================================================


@requires_postgres
class TestBudgetExpiry:
    """Stale reservations are flipped to 'expired' and stop counting."""

    @staticmethod
    def _insert_reservation(
        session, store_id: str, *, cost: float, ttl_seconds: int
    ) -> UsageRecord:
        now = datetime.utcnow()
        rec = UsageRecord(
            store_id=store_id,
            conversation_id=f"conv_{_uid()}",
            request_id=_request_id(),
            route="chat",
            model=None,
            input_tokens=0,
            output_tokens=0,
            estimated_cost=cost,
            status="reserved",
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        return rec

    def test_expire_stale_flips_status_and_frees_active_usage(
        self, budget_store, db_session
    ):
        expired = self._insert_reservation(
            db_session, budget_store.id, cost=0.0005, ttl_seconds=-30
        )
        live = self._insert_reservation(
            db_session, budget_store.id, cost=0.0002, ttl_seconds=300
        )

        repo = UsageRepository(db_session)
        count = repo.expire_stale_reservations(store_id=budget_store.id)

        assert count >= 1

        db_session.refresh(expired)
        db_session.refresh(live)
        assert expired.status == "expired"
        assert live.status == "reserved"

        # Active reserved usage excludes the expired reservation and
        # includes only the live one.
        assert repo.get_active_reserved_usage(
            budget_store.id
        ) == pytest.approx(0.0002)

    def test_expired_reservations_free_budget_for_new_reservations(
        self, budget_store, db_session
    ):
        # A reservation that already exceeded its TTL holds the whole
        # 0.001 budget on paper...
        stale = self._insert_reservation(
            db_session, budget_store.id, cost=0.001, ttl_seconds=-30
        )
        assert stale.status == "reserved"

        repo = UsageRepository(db_session)
        # ...but reserve_budget expires stale rows before the budget
        # check, so a fresh full-budget reservation still succeeds.
        rec = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=_request_id(),
            route="chat",
            model="test-model",
            estimated_cost=0.001,
        )
        assert rec is not None
        assert rec.status == "reserved"

        db_session.refresh(stale)
        assert stale.status == "expired"


# =================================================================
# 3. Idempotency
# =================================================================


@requires_postgres
class TestBudgetIdempotency:
    """Same request_id must never create a second usage row."""

    def test_reserve_budget_twice_same_request_id_returns_same_record(
        self, budget_store, db_session
    ):
        rid = _request_id()
        repo = UsageRepository(db_session)

        first = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid,
            route="chat",
            model="test-model",
            estimated_cost=0.0004,
        )
        assert first is not None

        # Second call with the SAME request_id (and even a different
        # cost) must return the existing record, not create a row.
        second = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid,
            route="chat",
            model="test-model",
            estimated_cost=0.0009,
        )
        assert second is not None
        assert second.id == first.id
        assert float(second.estimated_cost) == pytest.approx(
            float(first.estimated_cost)
        )

        rows = (
            db_session.query(UsageRecord)
            .filter(UsageRecord.request_id == rid)
            .all()
        )
        assert len(rows) == 1

    def test_reserve_after_expiry_replaces_expired_row(
        self, budget_store, db_session
    ):
        rid = _request_id()
        repo = UsageRepository(db_session)

        first = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid,
            route="chat",
            model="test-model",
            estimated_cost=0.0005,
        )
        assert first is not None

        # Simulate the TTL passing.
        first.status = "expired"
        first.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db_session.commit()

        second = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid,
            route="chat",
            model="test-model",
            estimated_cost=0.0005,
        )
        assert second is not None
        assert second.status == "reserved"
        assert second.id != first.id  # old row deleted, fresh one created

        rows = (
            db_session.query(UsageRecord)
            .filter(UsageRecord.request_id == rid)
            .all()
        )
        assert len(rows) == 1  # no duplicate survived

    def test_record_twice_same_request_id_no_duplicate(
        self, budget_store, db_session
    ):
        rid = _request_id()
        repo = UsageRepository(db_session)

        first = repo.record(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid,
            route="chat",
            model="test-model",
            input_tokens=10,
            output_tokens=5,
            estimated_cost=0.25,
        )
        assert first is not None
        assert first.status == "completed"

        second = repo.record(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid,
            route="chat",
            model="test-model",
            input_tokens=999,
            output_tokens=999,
            estimated_cost=9.9,
        )
        assert second is not None
        assert second.id == first.id
        # The existing record is returned untouched.
        assert float(second.estimated_cost) == pytest.approx(0.25)
        assert second.input_tokens == 10

        rows = (
            db_session.query(UsageRecord)
            .filter(UsageRecord.request_id == rid)
            .all()
        )
        assert len(rows) == 1


# =================================================================
# 4. Overspend rejection
# =================================================================


@requires_postgres
class TestBudgetOverspendRejected:
    """A reservation that would exceed the monthly budget returns None."""

    def test_second_reservation_beyond_budget_rejected(
        self, budget_store, db_session
    ):
        repo = UsageRepository(db_session)

        first = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=_request_id(),
            route="chat",
            model="test-model",
            estimated_cost=0.001,  # exactly the budget
        )
        assert first is not None
        assert first.status == "reserved"

        rejected = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=_request_id(),  # different request_id on purpose
            route="chat",
            model="test-model",
            estimated_cost=0.001,
        )
        assert rejected is None  # budget exhausted (active reservation counts)

        rows = (
            db_session.query(UsageRecord)
            .filter(UsageRecord.store_id == budget_store.id)
            .all()
        )
        assert len(rows) == 1  # the rejected attempt left no row behind
        assert repo.get_monthly_committed_usage(
            budget_store.id
        ) == pytest.approx(0.001)

    def test_completed_usage_also_counts_toward_budget(
        self, budget_store, db_session
    ):
        repo = UsageRepository(db_session)

        rid1 = _request_id()
        first = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=rid1,
            route="chat",
            model="test-model",
            estimated_cost=0.001,
        )
        assert first is not None

        done = repo.finalize_budget_reservation(
            request_id=rid1,
            input_tokens=10,
            output_tokens=5,
            actual_cost=0.0004,
        )
        assert done is not None
        assert done.status == "completed"

        # 0.0004 completed + 0.0007 would be 0.0011 > 0.001 -> rejected.
        assert (
            repo.reserve_budget(
                store_id=budget_store.id,
                conversation_id=f"conv_{_uid()}",
                request_id=_request_id(),
                route="chat",
                model="test-model",
                estimated_cost=0.0007,
            )
            is None
        )

        # 0.0004 completed + 0.0005 = 0.0009 <= 0.001 -> accepted.
        ok = repo.reserve_budget(
            store_id=budget_store.id,
            conversation_id=f"conv_{_uid()}",
            request_id=_request_id(),
            route="chat",
            model="test-model",
            estimated_cost=0.0005,
        )
        assert ok is not None
        assert ok.status == "reserved"


# =================================================================
# 5. Lock serialization (the race test)
# =================================================================


@requires_postgres
class TestBudgetLockSerialization:
    """
    Concurrent reserve_budget calls for the same store must be
    serialized by the FOR UPDATE row lock: combined cost over the
    budget must never lead to two successful reservations.
    """

    def test_concurrent_reservations_only_one_succeeds(self, budget_store):
        results: list = []
        errors: list = []
        barrier = threading.Barrier(2, timeout=15)

        def worker(request_id: str) -> None:
            try:
                # Dedicated session/connection per thread.
                with SessionLocal() as session:
                    repo = UsageRepository(session)
                    barrier.wait(timeout=15)
                    rec = repo.reserve_budget(
                        store_id=budget_store.id,
                        conversation_id=f"conv_{_uid()}",
                        request_id=request_id,
                        route="chat",
                        model="test-model",
                        estimated_cost=0.001,
                    )
                    results.append((request_id, rec))
            except Exception as exc:  # pragma: no cover - diagnostic path
                errors.append(f"{request_id}: {exc!r}")

        rid_a = _request_id()
        rid_b = _request_id()

        threads = [
            threading.Thread(target=worker, args=(rid_a,)),
            threading.Thread(target=worker, args=(rid_b,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"worker threads failed: {errors}"
        assert len(results) == 2, "both workers must have finished"

        succeeded = [rec for _, rec in results if rec is not None]
        failed_ids = [rid for rid, rec in results if rec is None]

        # Exactly one winner: the FOR UPDATE lock serializes the
        # check-then-insert so 0.001 + 0.001 can never both fit.
        assert len(succeeded) == 1

        total = sum(float(rec.estimated_cost) for rec in succeeded)
        budget = float(budget_store.monthly_budget)
        assert total <= budget + 1e-9

        # The loser must not have persisted anything.
        for rid in failed_ids:
            with SessionLocal() as session:
                leftover = (
                    session.query(UsageRecord)
                    .filter(UsageRecord.request_id == rid)
                    .all()
                )
            assert leftover == []

    def test_reserve_budget_blocks_on_locked_store_row(self, budget_store):
        """
        Direct lock-semantics check: while another transaction holds
        FOR UPDATE on the store row, reserve_budget in a second session
        cannot proceed — it blocks and hits the configured lock_timeout
        instead of skipping the lock.
        """
        rid = _request_id()

        with SessionLocal() as holder:
            locked = (
                holder.query(Store)
                .filter(Store.id == budget_store.id)
                .with_for_update()
                .first()
            )
            assert locked is not None

            with SessionLocal() as waiter:
                # Short session-level lock timeout; survives the internal
                # commits reserve_budget performs before taking the lock.
                waiter.execute(text("SET lock_timeout = '800ms'"))
                repo = UsageRepository(waiter)

                with pytest.raises(OperationalError) as exc_info:
                    repo.reserve_budget(
                        store_id=budget_store.id,
                        conversation_id=f"conv_{_uid()}",
                        request_id=rid,
                        route="chat",
                        model="test-model",
                        estimated_cost=0.001,
                    )

                msg = str(exc_info.value).lower()
                assert (
                    "lock" in msg or "55p03" in msg or "cancel" in msg
                ), f"unexpected error while waiting for lock: {msg}"

                waiter.rollback()

            holder.rollback()  # release the FOR UPDATE lock

        # Once the lock is gone the identical reservation succeeds.
        with SessionLocal() as session:
            rec = UsageRepository(session).reserve_budget(
                store_id=budget_store.id,
                conversation_id=f"conv_{_uid()}",
                request_id=rid,
                route="chat",
                model="test-model",
                estimated_cost=0.001,
            )
            assert rec is not None
            assert rec.status == "reserved"


# =================================================================
# 6. Rate limiter (real Redis, atomic Lua)
# =================================================================


@requires_redis
class TestRateLimiterAtomic:
    """_check_limit against real Redis: atomic INCR/EXPIRE via Lua."""

    @pytest_asyncio.fixture
    async def rate_env(self, monkeypatch):
        """
        Fresh Redis client per test bound to the current event loop,
        injected over app.core.rate_limit.redis_client. All keys are
        namespaced test_3b:* and removed on teardown.
        """
        client = redis_async.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        monkeypatch.setattr(rate_limit, "redis_client", client)

        # Clean slate for our namespace.
        stale = [k async for k in client.scan_iter(match="test_3b:*")]
        if stale:
            await client.delete(*stale)

        yield client

        try:
            keys = [k async for k in client.scan_iter(match="test_3b:*")]
            if keys:
                await client.delete(*keys)
        finally:
            await client.aclose()

    @staticmethod
    def _key() -> str:
        return f"test_3b:{_uid()}:minute:{int(time.time() // 60)}"

    @pytest.mark.asyncio
    async def test_increments_then_raises_429_with_headers(self, rate_env):
        key = self._key()
        limit = 3

        for i in range(limit):
            result = await rate_limit._check_limit(
                key=key, limit=limit, label="Store"
            )
            assert result["limit"] == limit
            assert result["remaining"] == limit - (i + 1)
            assert result["reset"] >= int(time.time())

        # (limit + 1)-th call must be rejected.
        with pytest.raises(HTTPException) as exc_info:
            await rate_limit._check_limit(key=key, limit=limit, label="Store")

        exc = exc_info.value
        assert exc.status_code == 429
        assert "rate limit exceeded" in str(exc.detail).lower()

        headers = exc.headers
        assert headers is not None
        assert int(headers["Retry-After"]) > 0
        assert headers["X-RateLimit-Limit"] == str(limit)
        assert headers["X-RateLimit-Remaining"] == "0"
        assert int(headers["X-RateLimit-Reset"]) >= int(time.time())

        # Rejection must not leave the key in a broken state.
        ttl = await rate_env.ttl(key)
        assert 0 < ttl <= 61

    @pytest.mark.asyncio
    async def test_key_ttl_always_positive_after_calls(self, rate_env):
        key = self._key()
        limit = 10

        for _ in range(5):
            await rate_limit._check_limit(key=key, limit=limit, label="Store")
            ttl = await rate_env.ttl(key)
            # The Lua script guarantees the counter always carries a TTL
            # (never -1 / -2), so the key can never become a permanent 429.
            assert 0 < ttl <= 61

    @pytest.mark.asyncio
    async def test_recovers_key_left_without_ttl(self, rate_env):
        """
        The ttl < 0 branch of the Lua script: a key that lost its TTL
        (the exact failure mode the atomicity fix targets) is re-EXPIREd
        on the next limiter call.
        """
        key = self._key()

        # Simulate a legacy key without expiry.
        await rate_env.set(key, "4")
        assert await rate_env.ttl(key) == -1

        result = await rate_limit._check_limit(
            key=key, limit=10, label="Store"
        )
        assert result["remaining"] == 5  # count went 4 -> 5, limit 10

        ttl = await rate_env.ttl(key)
        assert 0 < ttl <= 61

    @pytest.mark.asyncio
    async def test_independent_keys_count_separately(self, rate_env):
        key_a = self._key()
        key_b = self._key()

        await rate_limit._check_limit(key=key_a, limit=5, label="Store")
        await rate_limit._check_limit(key=key_a, limit=5, label="Store")
        result_b = await rate_limit._check_limit(
            key=key_b, limit=5, label="Store"
        )
        assert result_b["remaining"] == 4  # untouched by key_a's count

        count_a = await rate_env.get(key_a)
        count_b = await rate_env.get(key_b)
        assert count_a == "2"
        assert count_b == "1"


# =================================================================
# 7. Client IP resolution
# =================================================================


class TestClientIPResolution:
    """X-Forwarded-For is trusted only from trusted proxy peers."""

    def test_direct_peer_with_spoofed_xff_is_ignored(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "")
        # Client connects directly and sends a fake XFF: the header is
        # client-controlled, so the TCP peer is returned.
        assert resolve_client_ip("203.0.113.9", "1.2.3.4") == "203.0.113.9"
        assert resolve_client_ip(
            "203.0.113.9", "1.2.3.4, 5.6.7.8"
        ) == "203.0.113.9"

    def test_trusted_proxy_peer_extracts_client(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.1")
        # "client, proxy" — the rightmost untrusted hop is the client.
        assert resolve_client_ip(
            "10.0.0.1", "203.0.113.5, 10.0.0.1"
        ) == "203.0.113.5"

    def test_untrusted_peer_takes_rightmost_untrusted_hop(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.1")
        # Both chain entries are untrusted: rightmost one wins.
        assert resolve_client_ip(
            "10.0.0.1", "9.9.9.9, 6.6.6.6"
        ) == "6.6.6.6"

    def test_all_trusted_chain_falls_back_to_leftmost(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.1,10.0.0.2")
        # Every hop is a trusted proxy: the leftmost entry is the best
        # available identity.
        assert resolve_client_ip(
            "10.0.0.1", "10.0.0.2, 10.0.0.1"
        ) == "10.0.0.2"

    def test_no_xff_returns_peer(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.1")
        assert resolve_client_ip("10.0.0.1", None) == "10.0.0.1"
        assert resolve_client_ip("192.168.1.5", None) == "192.168.1.5"

    def test_empty_or_blank_xff_returns_peer(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.1")
        assert resolve_client_ip("10.0.0.1", "") == "10.0.0.1"
        assert resolve_client_ip("10.0.0.1", " , ") == "10.0.0.1"

    def test_null_peer_falls_back_to_unknown(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "")
        assert resolve_client_ip(None, None) == "unknown"

    def test_get_trusted_proxies_parsing(self, monkeypatch):
        monkeypatch.setattr(
            settings, "trusted_proxies", " 10.0.0.1 , 10.0.0.2 ,"
        )
        assert get_trusted_proxies() == ["10.0.0.1", "10.0.0.2"]
        monkeypatch.setattr(settings, "trusted_proxies", "")
        assert get_trusted_proxies() == []


# =================================================================
# 8. Auth prefix enforcement
# =================================================================


@requires_postgres
class TestAuthPrefixEnforcement:
    """
    authenticate_api_key and get_api_key must enforce identical rules:
    reject non-pk_ keys (401), accept only valid unrevoked hashes.
    """

    @pytest.fixture
    def auth_env(self, db_session):
        uid = _uid()
        store = Store(
            name=f"test_3b_{uid}",
            monthly_budget=Decimal("1.000000"),
            status="active",
        )
        raw_valid = f"pk_live_test_3b_{uid}"
        raw_revoked = f"pk_live_revoked_{uid}"

        db_session.add(store)
        db_session.flush()  # assign the uuid PK before referencing store.id

        key_valid = APIKey(
            store_id=store.id,
            key_prefix=raw_valid[:16],
            key_hash=hash_api_key(raw_valid),
            name="test valid key",
        )
        key_revoked = APIKey(
            store_id=store.id,
            key_prefix=raw_revoked[:16],
            key_hash=hash_api_key(raw_revoked),
            name="test revoked key",
            revoked_at=datetime.utcnow(),
        )

        db_session.add_all([store, key_valid, key_revoked])
        db_session.commit()
        db_session.refresh(store)

        try:
            yield {
                "uid": uid,
                "store": store,
                "raw_valid": raw_valid,
                "raw_revoked": raw_revoked,
                "key_valid_id": key_valid.id,
            }
        finally:
            db_session.rollback()
            _cleanup_store(store.id)

    @pytest.mark.asyncio
    async def test_valid_key_accepted_by_both_dependencies(
        self, auth_env, db_session
    ):
        via_dependency = await authenticate_api_key(
            x_api_key=auth_env["raw_valid"], db=db_session
        )
        via_api_key = await get_api_key(
            x_api_key=auth_env["raw_valid"], db=db_session
        )

        assert via_dependency.id == auth_env["key_valid_id"]
        assert via_api_key.id == auth_env["key_valid_id"]
        assert via_dependency.store_id == auth_env["store"].id
        assert via_api_key.store_id == auth_env["store"].id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kind,expected_detail",
        [
            ("missing", "API key required"),
            ("bad_prefix", "Invalid API key"),
            ("unknown", "Invalid or revoked API key"),
            ("revoked", "Invalid or revoked API key"),
        ],
    )
    async def test_rejections_consistent_across_dependencies(
        self, auth_env, db_session, kind, expected_detail
    ):
        uid = auth_env["uid"]
        inputs = {
            "missing": None,
            "bad_prefix": f"sk_live_{uid}",  # valid-looking but wrong prefix
            "unknown": f"pk_live_unknown_{uid}",  # pk_ but not in DB
            "revoked": auth_env["raw_revoked"],
        }
        api_key_value = inputs[kind]

        for auth_fn in (authenticate_api_key, get_api_key):
            with pytest.raises(HTTPException) as exc_info:
                await auth_fn(x_api_key=api_key_value, db=db_session)
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == expected_detail

    @pytest.mark.asyncio
    async def test_bad_prefix_rejected_before_hash_lookup(
        self, auth_env, db_session
    ):
        """
        A non-pk_ key that coincidentally hashes to nothing in the DB
        must yield the format error ("Invalid API key"), proving the
        prefix check runs BEFORE the hash lookup in both dependencies.
        """
        bogus = f"sk_totally_wrong_{_uid()}"

        for auth_fn in (authenticate_api_key, get_api_key):
            with pytest.raises(HTTPException) as exc_info:
                await auth_fn(x_api_key=bogus, db=db_session)
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Invalid API key"
