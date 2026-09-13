import logging

from datetime import (
    datetime,
    timedelta,
)

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Store
from app.usage.models import UsageRecord
from app.usage.plan_quotas import get_monthly_request_quota

logger = logging.getLogger("app.usage")


class UsageRepository:

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

    # ---------------------------------
    # Current month boundaries
    # ---------------------------------

    def _month_bounds(self):

        now = datetime.utcnow()

        month_start = datetime(
            now.year,
            now.month,
            1,
        )

        if now.month == 12:

            next_month = datetime(
                now.year + 1,
                1,
                1,
            )

        else:

            next_month = datetime(
                now.year,
                now.month + 1,
                1,
            )

        return (
            month_start,
            next_month,
        )

    # ---------------------------------
    # Expired reservations
    # ---------------------------------

    def expire_stale_reservations(
        self,
        store_id: str | None = None,
        commit: bool = True,
    ) -> int:
        """
        Expire reservations whose TTL has passed.

        `commit=False` runs the expiry inside the caller's
        transaction. This is REQUIRED when invoked while a
        `FOR UPDATE` row lock is held (see `reserve_budget`):
        committing mid-transaction would release the lock and
        reopen the concurrent-overspend race.
        """

        now = datetime.utcnow()

        query = (
            self.db.query(
                UsageRecord
            )
            .filter(
                UsageRecord.status
                == "reserved",
                UsageRecord.expires_at
                != None,
                UsageRecord.expires_at
                <= now,
            )
        )

        if store_id is not None:

            query = query.filter(
                UsageRecord.store_id
                == store_id
            )

        records = query.all()

        for record in records:

            record.status = "expired"

        if records and commit:

            self.db.commit()

        return len(records)

    # ---------------------------------
    # Monthly completed usage
    # ---------------------------------

    def get_monthly_usage(
        self,
        store_id: str,
    ) -> float:

        (
            month_start,
            next_month,
        ) = self._month_bounds()

        total = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        UsageRecord.estimated_cost
                    ),
                    0.0,
                )
            )
            .filter(
                UsageRecord.store_id
                == store_id,

                UsageRecord.status
                == "completed",

                UsageRecord.created_at
                >= month_start,

                UsageRecord.created_at
                < next_month,
            )
            .scalar()
        )

        return float(
            total or 0.0
        )

    # ---------------------------------
    # Active reserved usage
    # ---------------------------------

    def get_active_reserved_usage(
        self,
        store_id: str,
    ) -> float:

        self.expire_stale_reservations(
            store_id=store_id
        )

        (
            month_start,
            next_month,
        ) = self._month_bounds()

        now = datetime.utcnow()

        total = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        UsageRecord.estimated_cost
                    ),
                    0.0,
                )
            )
            .filter(
                UsageRecord.store_id
                == store_id,

                UsageRecord.status
                == "reserved",

                UsageRecord.created_at
                >= month_start,

                UsageRecord.created_at
                < next_month,

                UsageRecord.expires_at
                != None,

                UsageRecord.expires_at
                > now,
            )
            .scalar()
        )

        return float(
            total or 0.0
        )

    # ---------------------------------
    # Total committed usage
    # ---------------------------------

    def get_monthly_committed_usage(
        self,
        store_id: str,
    ) -> float:

        completed = (
            self.get_monthly_usage(
                store_id
            )
        )

        reserved = (
            self.get_active_reserved_usage(
                store_id
            )
        )

        return (
            completed
            + reserved
        )

    # ---------------------------------
    # Monthly completed request count
    # ---------------------------------

    def get_monthly_request_count(
        self,
        store_id: str,
    ) -> int:

        (
            month_start,
            next_month,
        ) = self._month_bounds()

        total = (
            self.db.query(
                func.count(
                    UsageRecord.id
                )
            )
            .filter(
                UsageRecord.store_id
                == store_id,

                UsageRecord.status
                == "completed",

                UsageRecord.created_at
                >= month_start,

                UsageRecord.created_at
                < next_month,
            )
            .scalar()
        )

        return int(
            total or 0
        )

    # ---------------------------------
    # Active reserved request count
    # ---------------------------------

    def get_active_reserved_request_count(
        self,
        store_id: str,
    ) -> int:

        self.expire_stale_reservations(
            store_id=store_id
        )

        (
            month_start,
            next_month,
        ) = self._month_bounds()

        now = datetime.utcnow()

        total = (
            self.db.query(
                func.count(
                    UsageRecord.id
                )
            )
            .filter(
                UsageRecord.store_id
                == store_id,

                UsageRecord.status
                == "reserved",

                UsageRecord.created_at
                >= month_start,

                UsageRecord.created_at
                < next_month,

                UsageRecord.expires_at
                != None,

                UsageRecord.expires_at
                > now,
            )
            .scalar()
        )

        return int(
            total or 0
        )

    # ---------------------------------
    # Total committed request count
    # ---------------------------------

    def get_monthly_committed_request_count(
        self,
        store_id: str,
    ) -> int:

        completed = (
            self.get_monthly_request_count(
                store_id
            )
        )

        reserved = (
            self.get_active_reserved_request_count(
                store_id
            )
        )

        return (
            completed
            + reserved
        )

    # ---------------------------------
    # Create completed record
    # ---------------------------------

    def record(
        self,
        *,
        store_id: str,
        conversation_id: str,
        request_id: str,
        route: str,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        latency_ms: int = 0,
        cache_hit: bool = False,
    ) -> UsageRecord:

        # Prevent duplicate request records.
        existing = (
            self.db.query(
                UsageRecord
            )
            .filter(
                UsageRecord.request_id
                == request_id
            )
            .first()
        )

        if existing is not None:

            return existing

        record = UsageRecord(
            store_id=store_id,
            conversation_id=conversation_id,
            request_id=request_id,
            route=route,
            model=model,
            input_tokens=max(
                int(input_tokens),
                0,
            ),
            output_tokens=max(
                int(output_tokens),
                0,
            ),
            estimated_cost=max(
                float(estimated_cost),
                0.0,
            ),
            latency_ms=max(
                int(latency_ms),
                0,
            ),
            cache_hit=bool(
                cache_hit
            ),
            status="completed",
            expires_at=None,
        )

        self.db.add(
            record
        )

        self.db.commit()

        self.db.refresh(
            record
        )

        return record

    # ---------------------------------
    # Reserve monthly budget
    # ---------------------------------

    def reserve_budget(
        self,
        *,
        store_id: str,
        conversation_id: str,
        request_id: str,
        route: str,
        model: str | None,
        estimated_cost: float,
        reservation_ttl_seconds: int = 300,
    ) -> UsageRecord | None:

        if estimated_cost < 0:

            raise ValueError(
                "estimated_cost cannot be negative"
            )

        # ---------------------------------
        # Idempotency
        # ---------------------------------

        existing = (
            self.db.query(
                UsageRecord
            )
            .filter(
                UsageRecord.request_id
                == request_id
            )
            .first()
        )

        if existing is not None:

            if existing.status == "expired":

                self.db.delete(
                    existing
                )

                self.db.commit()

            else:

                return existing

        # ---------------------------------
        # Expire stale reservations
        # ---------------------------------
        #
        # Runs as its own committed transaction,
        # BEFORE the store row lock is taken. Doing
        # this inside the locked section would either
        # (a) commit mid-transaction and release the
        # lock, or (b) leave expiry changes vulnerable
        # to the caller's rollback paths.

        self.expire_stale_reservations(
            store_id=store_id,
            commit=True,
        )

        # ---------------------------------
        # Lock store row
        # ---------------------------------

        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id
            )
            .with_for_update()
            .first()
        )

        if store is None:

            self.db.rollback()

            return None

        monthly_budget = float(
            store.monthly_budget
        )

        # Stale reservations were already expired and
        # committed BEFORE the lock was taken; the two
        # sums below therefore run against current data
        # while the `FOR UPDATE` lock serializes
        # concurrent reserve_budget calls.

        (
            month_start,
            next_month,
        ) = self._month_bounds()

        now = datetime.utcnow()

        # ---------------------------------
        # Completed usage
        # ---------------------------------

        completed = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        UsageRecord.estimated_cost
                    ),
                    0.0,
                )
            )
            .filter(
                UsageRecord.store_id
                == store_id,

                UsageRecord.status
                == "completed",

                UsageRecord.created_at
                >= month_start,

                UsageRecord.created_at
                < next_month,
            )
            .scalar()
        )

        completed = float(
            completed or 0.0
        )

        # ---------------------------------
        # Active reservations
        # ---------------------------------

        reserved = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        UsageRecord.estimated_cost
                    ),
                    0.0,
                )
            )
            .filter(
                UsageRecord.store_id
                == store_id,

                UsageRecord.status
                == "reserved",

                UsageRecord.created_at
                >= month_start,

                UsageRecord.created_at
                < next_month,

                UsageRecord.expires_at
                != None,

                UsageRecord.expires_at
                > now,
            )
            .scalar()
        )

        reserved = float(
            reserved or 0.0
        )

        committed = (
            completed
            + reserved
        )

        # ---------------------------------
        # Budget check
        # ---------------------------------

        if (
            committed
            + estimated_cost
            > monthly_budget
        ):

            self.db.rollback()

            return None

        # ---------------------------------
        # Plan request-quota check
        # ---------------------------------
        #
        # A separate cap from the dollar budget above:
        # "starter plan = N requests / month" regardless
        # of how cheap each individual request is. Counted
        # under the same store row lock (and against the
        # same completed + active-reserved rows) as the
        # budget check, so bursts of concurrent requests
        # can't slip past the monthly cap either.

        request_quota = get_monthly_request_quota(
            store.plan
        )

        if request_quota is not None:

            completed_requests = (
                self.db.query(
                    func.count(
                        UsageRecord.id
                    )
                )
                .filter(
                    UsageRecord.store_id
                    == store_id,

                    UsageRecord.status
                    == "completed",

                    UsageRecord.created_at
                    >= month_start,

                    UsageRecord.created_at
                    < next_month,
                )
                .scalar()
            )

            completed_requests = int(
                completed_requests or 0
            )

            reserved_requests = (
                self.db.query(
                    func.count(
                        UsageRecord.id
                    )
                )
                .filter(
                    UsageRecord.store_id
                    == store_id,

                    UsageRecord.status
                    == "reserved",

                    UsageRecord.created_at
                    >= month_start,

                    UsageRecord.created_at
                    < next_month,

                    UsageRecord.expires_at
                    != None,

                    UsageRecord.expires_at
                    > now,
                )
                .scalar()
            )

            reserved_requests = int(
                reserved_requests or 0
            )

            committed_requests = (
                completed_requests
                + reserved_requests
            )

            if (
                committed_requests + 1
                > request_quota
            ):

                self.db.rollback()

                logger.info(
                    "Monthly request quota exceeded for "
                    "store %s (plan=%s, quota=%s, "
                    "committed=%s)",
                    store_id,
                    store.plan,
                    request_quota,
                    committed_requests,
                )

                return None

        # ---------------------------------
        # Create reservation
        # ---------------------------------

        reservation = UsageRecord(
            store_id=store_id,
            conversation_id=conversation_id,
            request_id=request_id,
            route=route,
            model=model,
            input_tokens=0,
            output_tokens=0,
            estimated_cost=float(
                estimated_cost
            ),
            latency_ms=0,
            cache_hit=False,
            status="reserved",
            expires_at=(
                now
                + timedelta(
                    seconds=reservation_ttl_seconds
                )
            ),
        )

        self.db.add(
            reservation
        )

        self.db.commit()

        self.db.refresh(
            reservation
        )

        return reservation

    # ---------------------------------
    # Finalize reservation
    # ---------------------------------

    def finalize_budget_reservation(
        self,
        *,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
        actual_cost: float,
        latency_ms: int = 0,
        cache_hit: bool = False,
    ) -> UsageRecord | None:

        reservation = (
            self.db.query(
                UsageRecord
            )
            .filter(
                UsageRecord.request_id
                == request_id
            )
            .first()
        )

        if reservation is None:

            return None

        reservation.input_tokens = max(
            int(input_tokens),
            0,
        )

        reservation.output_tokens = max(
            int(output_tokens),
            0,
        )

        reservation.estimated_cost = max(
            float(actual_cost),
            0.0,
        )

        reservation.latency_ms = max(
            int(latency_ms),
            0,
        )

        reservation.cache_hit = bool(
            cache_hit
        )

        reservation.status = (
            "completed"
        )

        reservation.expires_at = None

        self.db.commit()

        self.db.refresh(
            reservation
        )

        return reservation

    # ---------------------------------
    # Mark reservation failed
    # ---------------------------------

    def fail_budget_reservation(
        self,
        *,
        request_id: str,
    ) -> UsageRecord | None:

        reservation = (
            self.db.query(
                UsageRecord
            )
            .filter(
                UsageRecord.request_id
                == request_id
            )
            .first()
        )

        if reservation is None:

            return None

        reservation.status = (
            "failed"
        )

        reservation.estimated_cost = 0.0

        reservation.input_tokens = 0

        reservation.output_tokens = 0

        reservation.expires_at = None

        self.db.commit()

        self.db.refresh(
            reservation
        )

        return reservation

    # ---------------------------------
    # Get a reservation
    # ---------------------------------

    def get_by_request_id(
        self,
        request_id: str,
    ) -> UsageRecord | None:

        return (
            self.db.query(
                UsageRecord
            )
            .filter(
                UsageRecord.request_id
                == request_id
            )
            .first()
        )