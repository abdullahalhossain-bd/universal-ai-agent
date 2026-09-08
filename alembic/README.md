# Database migrations (Alembic)

Before this, schema changes only happened through
`Base.metadata.create_all()` at app startup (`AUTO_CREATE_TABLES=true`,
the default). That call can add a table that doesn't exist yet, but it
**can never alter an existing one** — rename/resize/retype a column,
add a `NOT NULL`, backfill data, drop a column. Once real merchant
data exists, any of those changes had no path except manual `ALTER
TABLE` by hand against production (or downtime + a dump/reload). This
directory replaces that with reviewable, ordered migrations.

## One-time setup per environment

`alembic/env.py` reads the DB connection from `app.core.config.settings`
(the same `DATABASE_URL` the app uses) — nothing DB-related needs to
be configured a second time in `alembic.ini`. It also needs
`CREDENTIAL_ENCRYPTION_KEY` set (importing the app's models imports
`app.datasources.service`'s dependencies), same as running the app.

## Day-to-day workflow

1. Change a model in `app/db/models.py`, `app/chat/models.py`,
   `app/usage/models.py`, or `app/knowledge/chunk.py` (the "Active ORM
   Models" set — see `app/main.py`).
2. Generate a migration from the diff:
   ```bash
   alembic revision --autogenerate -m "add stores.timezone"
   ```
3. **Read the generated file in `alembic/versions/` before committing
   it.** Autogenerate is a diffing tool, not a design tool — it won't
   notice a rename (it'll emit a drop + add, which loses data) and
   won't write a backfill for a new `NOT NULL` column. Rewrite those
   parts by hand; see the *Common cases* section below.
4. Apply it locally: `alembic upgrade head`.
5. Commit the migration file alongside the model change, in the same
   PR. A model change without a matching migration is exactly the bug
   this setup exists to catch — `tests/test_migrations.py` fails the
   build if they drift apart.

## Deploying

Run this as a deploy step, before the new app code starts serving
traffic:

```bash
alembic upgrade head
```

`AUTO_CREATE_TABLES` must be `false` wherever `ENVIRONMENT=production`
— `app/main.py`'s startup now refuses to boot otherwise, specifically
so this doesn't get skipped by accident.

## Adopting this on an existing database

If an environment's tables were created by `create_all()` (i.e. it has
every table but no `alembic_version` table), don't run `alembic
upgrade head` blind — `0001_baseline_schema` would try to `CREATE
TABLE` things that already exist and fail. Tell Alembic that database
is already at the baseline without re-running the DDL:

```bash
alembic stamp 0001
```

Then future `alembic upgrade head` runs apply only what comes after
0001. (Nothing to migrate yet on a brand-new database — `alembic
upgrade head` there runs `0001` for real and creates everything.)

## Common cases autogenerate gets wrong

- **Renaming a column/table**: autogenerate emits `drop` + `add`,
  which drops the data. Replace with `op.alter_column(...,
  new_column_name=...)` / `op.rename_table(...)`.
- **New `NOT NULL` column on a table with existing rows**: add it
  nullable, `op.execute(...)` an `UPDATE` to backfill, then a second
  migration to add the `NOT NULL` constraint. Doing all three in one
  step on a large table also holds a long lock — consider splitting
  across deploys for that reason alone.
- **`knowledge_chunks.embedding`**: type depends on whether the
  `pgvector` extension is enabled on the *target* database at
  migration time (see `_knowledge_embedding_column()` in
  `0001_baseline_schema.py`, which mirrors
  `app/knowledge/vector_support.py`'s runtime probe). If you add a
  migration that touches this table, generate/review it against a
  database with the same pgvector availability as production, not
  whatever's on your laptop.

## Sanity checks

- `alembic heads` should print exactly one revision. Two means someone
  branched migrations (two PRs both based off the same parent
  revision) — merge them into a single linear chain with `alembic
  merge`, don't just pick one.
- `tests/test_migrations.py` applies every migration to a scratch
  sqlite DB and asserts a fresh autogenerate diff against it is empty
  — i.e. the migration history and the ORM models actually agree.
