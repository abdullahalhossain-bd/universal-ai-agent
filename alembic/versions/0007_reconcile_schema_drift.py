"""reconcile production schema drift against current models

Root cause
----------
`0001_baseline_schema` is a *reconstruction* of the schema the models
describe (see its own docstring and `alembic/README.md`'s "Adopting
this on an existing database" section): environments that predate
this migration chain had their tables created by
`Base.metadata.create_all()` under older versions of the models, and
were brought under Alembic with `alembic stamp <rev>` rather than by
actually running the DDL. Running `0001..0006` against a fresh
database reproduces `Base.metadata` byte-for-byte (see
`tests/test_migrations.py`) — the chain itself is not the problem.

The problem is that at least one real environment was stamped onto
this chain (up to `0006_chat_images`) while its *actual* on-disk
schema still reflects that older, pre-baseline state. `alembic check`
against that database reports exactly the drift this migration fixes:

* a leftover `tenants` table from a pre-Store architecture — no
  active model defines it (see `app/ARCHITECTURE_CLEANUP.md`); the
  live `Store`/`APIKey` model pair has been the tenant boundary since
  before this migration chain existed.
* `api_keys.key_hash` missing its unique constraint.
* `products.quantity` still `INTEGER` instead of `Numeric(14, 3)`
  (fractional stock units, e.g. weight-based products).
* `products` missing `ix_products_store_id`.
* `stores.plan` / `stores.monthly_budget` / `usage_records.status`
  missing the server-side defaults the models now declare explicitly
  (see `app/db/models.py` / `app/usage/models.py` — added alongside
  this migration precisely so a non-ORM insert can't violate NOT
  NULL on these columns).
* `usage_records` carrying a duplicate/legacy `ux_usage_records_request_id`
  unique index alongside a non-unique `ix_usage_records_request_id`
  (the model/migration-0001 intent is exactly one index, unique).
* `usage_records` missing `ix_usage_records_created_at`.

A second, independent bug found while auditing every migration for
model/migration mismatches (not part of the originally reported diff,
but the same class of problem): **`0001_baseline_schema` and
`0005_datasources` both define `op.create_table("datasources", ...)`.**
`0005`'s copy guards itself with `if "datasources" not in
inspector.get_table_names()`, so in every real environment (0001
always runs before 0005) it is a silent no-op — 0001's version of the
table, which predates `app/db/models.py`'s `DataSource.name` /
`.active` / `.full_sync` / `.created_at` / `.updated_at`
`server_default=` values, is what actually exists. That's why those
columns are fixed below too, even though they weren't in the original
reported diff list — the same root cause (`alembic check` with
`compare_server_default=True`) flags them once the model declares
matching server defaults (this migration's sibling change in
`app/db/models.py`). `0005_datasources.py` itself is left as-is (with
an explanatory comment) rather than rewritten, since it has already
run in every environment that matters and rewriting an applied
migration's DDL is out of scope here; its defaults are simply
unreachable dead code.

Every step below is guarded by inspecting the live schema first, so
this migration is a safe no-op on any database that already matches
the baseline chain (e.g. a fresh database created by `0001..0006`,
or this project's own `tests/test_migrations.py`), and only mutates
what actually needs it on a genuinely drifted database. Nothing here
touches `stores`, `products`, `api_keys`, or `usage_records` row data
— see `scripts/backup_db.sh` for the recommended pre-migration backup
step regardless.

Revision ID: 0007_reconcile_drift
Revises: 0006_chat_images
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "0007_reconcile_drift"
down_revision: Union[str, None] = "0006_chat_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(inspector, table: str) -> set[str]:
    return {
        idx["name"]
        for idx in inspector.get_indexes(table)
        if idx.get("name")
    }


def _unique_constraint_names(inspector, table: str) -> set[str]:
    names = {
        uc["name"]
        for uc in inspector.get_unique_constraints(table)
        if uc.get("name")
    }
    # Postgres represents a plain UNIQUE column constraint as a
    # unique *index* under the hood as well; sqlite's inspector may
    # report it only via get_indexes(). Union both so the "does a
    # uniqueness guarantee already exist" check is dialect-agnostic.
    names |= {
        idx["name"]
        for idx in inspector.get_indexes(table)
        if idx.get("unique") and idx.get("name")
    }
    return names


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    is_postgres = conn.dialect.name == "postgresql"
    tables = set(inspector.get_table_names())

    # -------------------------------------------------------------
    # 1) Drop the obsolete `tenants` table.
    #
    # Confirmed dead: no active model (app.db.models, app.chat.models,
    # app.knowledge.chunk, app.usage.models — the set alembic/env.py
    # and app/main.py both import) defines it, nothing in app/ queries
    # it, and no column anywhere holds a foreign key into it. It is
    # leftover from a pre-Store tenant architecture. Dropped via a
    # real migration rather than a manual `DROP TABLE` in production,
    # per the project's own migration discipline.
    # -------------------------------------------------------------
    if "tenants" in tables:
        op.drop_table("tenants")

    # -------------------------------------------------------------
    # 2) api_keys.key_hash uniqueness.
    # -------------------------------------------------------------
    if "api_keys" in tables:
        existing_unique = _unique_constraint_names(inspector, "api_keys")
        # Re-inspect columns fresh in case step 1 changed catalog state.
        has_unique_on_key_hash = any(
            True
            for uc in sa.inspect(conn).get_unique_constraints("api_keys")
            if uc.get("column_names") == ["key_hash"]
        ) or any(
            idx.get("unique") and idx.get("column_names") == ["key_hash"]
            for idx in sa.inspect(conn).get_indexes("api_keys")
        )

        if not has_unique_on_key_hash:
            duplicates = conn.execute(
                text(
                    "SELECT key_hash FROM api_keys "
                    "GROUP BY key_hash HAVING COUNT(*) > 1"
                )
            ).fetchall()

            if duplicates:
                raise RuntimeError(
                    "Cannot add unique constraint on api_keys.key_hash: "
                    f"{len(duplicates)} duplicate key_hash value(s) exist. "
                    "This should never happen (key_hash is a SHA-256 of a "
                    "cryptographically random key) and indicates a deeper "
                    "problem — investigate before proceeding rather than "
                    "silently dropping rows."
                )

            with op.batch_alter_table("api_keys") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_api_keys_key_hash",
                    ["key_hash"],
                )
        del existing_unique  # inspected for clarity above; not otherwise used

    # -------------------------------------------------------------
    # 3) products.quantity: INTEGER -> Numeric(14, 3).
    # -------------------------------------------------------------
    if "products" in tables:
        columns = {
            col["name"]: col for col in inspector.get_columns("products")
        }
        quantity_col = columns.get("quantity")
        if quantity_col is not None and not isinstance(
            quantity_col["type"], sa.Numeric
        ):
            with op.batch_alter_table("products") as batch_op:
                batch_op.alter_column(
                    "quantity",
                    existing_type=sa.Integer(),
                    type_=sa.Numeric(precision=14, scale=3),
                    postgresql_using="quantity::numeric(14,3)",
                )

        # ---------------------------------------------------------
        # 4) products missing ix_products_store_id.
        # ---------------------------------------------------------
        product_indexes = _index_names(sa.inspect(conn), "products")
        if "ix_products_store_id" not in product_indexes:
            op.create_index(
                "ix_products_store_id",
                "products",
                ["store_id"],
                unique=False,
            )

    # -------------------------------------------------------------
    # 5) Server-side defaults matching the models
    #    (stores.plan, stores.monthly_budget, usage_records.status,
    #    and — see this file's module docstring — datasources.name /
    #    .active / .full_sync / .created_at / .updated_at, which
    #    were always created by 0001's copy of the table, not 0005's).
    # -------------------------------------------------------------
    if "stores" in tables:
        with op.batch_alter_table("stores") as batch_op:
            batch_op.alter_column(
                "plan",
                existing_type=sa.String(length=20),
                server_default="starter",
                existing_nullable=False,
            )
            batch_op.alter_column(
                "monthly_budget",
                existing_type=sa.Numeric(precision=12, scale=6),
                server_default="1.000000",
                existing_nullable=False,
            )

    if "datasources" in tables:
        with op.batch_alter_table("datasources") as batch_op:
            batch_op.alter_column(
                "name",
                existing_type=sa.String(length=100),
                server_default="default",
                existing_nullable=False,
            )
            batch_op.alter_column(
                "active",
                existing_type=sa.Boolean(),
                server_default=sa.true(),
                existing_nullable=False,
            )
            batch_op.alter_column(
                "full_sync",
                existing_type=sa.Boolean(),
                server_default=sa.true(),
                existing_nullable=False,
            )
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DateTime(),
                server_default=sa.func.now(),
                existing_nullable=False,
            )
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.DateTime(),
                server_default=sa.func.now(),
                existing_nullable=False,
            )

    if "usage_records" in tables:
        with op.batch_alter_table("usage_records") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=sa.String(length=20),
                server_default="completed",
                existing_nullable=False,
            )

        # -----------------------------------------------------------
        # 6) usage_records.request_id: drop the legacy/duplicate
        #    `ux_usage_records_request_id` index and make sure the
        #    canonical `ix_usage_records_request_id` is unique.
        # -----------------------------------------------------------
        usage_indexes = {
            idx["name"]: idx
            for idx in sa.inspect(conn).get_indexes("usage_records")
            if idx.get("name")
        }

        if "ux_usage_records_request_id" in usage_indexes:
            op.drop_index(
                "ux_usage_records_request_id",
                table_name="usage_records",
            )
            usage_indexes.pop("ux_usage_records_request_id", None)

        canonical = usage_indexes.get("ix_usage_records_request_id")
        if canonical is None:
            op.create_index(
                "ix_usage_records_request_id",
                "usage_records",
                ["request_id"],
                unique=True,
            )
        elif not canonical.get("unique"):
            op.drop_index(
                "ix_usage_records_request_id",
                table_name="usage_records",
            )
            op.create_index(
                "ix_usage_records_request_id",
                "usage_records",
                ["request_id"],
                unique=True,
            )

        # -----------------------------------------------------------
        # 7) usage_records missing ix_usage_records_created_at.
        # -----------------------------------------------------------
        usage_indexes = _index_names(sa.inspect(conn), "usage_records")
        if "ix_usage_records_created_at" not in usage_indexes:
            op.create_index(
                "ix_usage_records_created_at",
                "usage_records",
                ["created_at"],
                unique=False,
            )

    _ = is_postgres  # reserved for any future dialect-specific branch


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    # Server defaults: revert to "no server default", matching what
    # 0001-0006 produced.
    if "usage_records" in tables:
        with op.batch_alter_table("usage_records") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=sa.String(length=20),
                server_default=None,
                existing_nullable=False,
            )

        usage_indexes = _index_names(sa.inspect(conn), "usage_records")
        if "ix_usage_records_created_at" in usage_indexes:
            op.drop_index(
                "ix_usage_records_created_at", table_name="usage_records"
            )
        # The ux_/ix_ request_id cleanup and api_keys/products/stores
        # fixes are intentionally NOT reversed to their drifted state
        # (there is no drifted state to reproduce — these are
        # corrections, not features). `ix_usage_records_request_id`
        # stays unique=True on downgrade, matching 0001's own intent.

    if "stores" in tables:
        with op.batch_alter_table("stores") as batch_op:
            batch_op.alter_column(
                "plan",
                existing_type=sa.String(length=20),
                server_default=None,
                existing_nullable=False,
            )
            batch_op.alter_column(
                "monthly_budget",
                existing_type=sa.Numeric(precision=12, scale=6),
                server_default=None,
                existing_nullable=False,
            )

    if "datasources" in tables:
        with op.batch_alter_table("datasources") as batch_op:
            for col, existing_type in (
                ("name", sa.String(length=100)),
                ("active", sa.Boolean()),
                ("full_sync", sa.Boolean()),
                ("created_at", sa.DateTime()),
                ("updated_at", sa.DateTime()),
            ):
                batch_op.alter_column(
                    col,
                    existing_type=existing_type,
                    server_default=None,
                    existing_nullable=False,
                )

    # Note: the `tenants` table drop, the products.quantity type
    # change, and the api_keys.key_hash / ix_products_store_id
    # additions are intentionally NOT reversed here — they correct
    # the schema to match the models, and reintroducing the drift
    # (including recreating an empty, model-less `tenants` table)
    # would just reproduce the original bug on downgrade.
