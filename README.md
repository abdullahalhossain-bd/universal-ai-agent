# Universal Commerce AI Agent

A multi-tenant SaaS platform that lets merchants add an AI shopping
assistant to their own websites.

```
Merchant signup/login → Dashboard → Store → Add Website / Product DB
  → discovery/crawl → products + knowledge stored & indexed
  → API key + embeddable widget on the merchant's site
  → customer asks product/site questions
  → intent detection → tenant-scoped search → grounded answer
```

**Stack**: FastAPI · PostgreSQL (+pgvector) · Redis (Streams queue) ·
SQLAlchemy · Alembic · React (Vite) merchant dashboard · vanilla-JS
embeddable widget · Groq LLM (optional — the chat has a deterministic,
store-data-grounded fallback when no LLM key is configured).

---

## Architecture (what runs where)

| Process | Start command | Purpose |
| --- | --- | --- |
| API | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | REST API, dashboard auth, chat endpoints, static widget/chat UIs |
| Worker | `python -m app.sync.worker` | Redis Streams consumer: website crawls, product syncs, embeddings. Per-datasource locks, bounded retries, dead-letter queue, stale-message reclaim (XAUTOCLAIM) |
| Scheduler | runs inside the worker loop (default) or standalone `python -m app.sync.scheduler` | Re-enqueues datasources past their recrawl interval |
| Dashboard | `cd frontend-dashboard && npm run dev` (or build `dist/`) | Merchant console |

`RUN_SYNC_INLINE` (default **true**) starts a worker + scheduler inside the
API process — convenient for single-process local dev. In any deployment
with a dedicated worker container, set `RUN_SYNC_INLINE=false` (both
docker-compose files already do) or every job runs twice.

Key directories:

- `app/api/routes/` + `app/chat/router.py` — all HTTP endpoints
- `app/auth/` — merchant JWT sessions, inbox cookie+CSRF, platform-admin
  JWT, public `pk_live_…` API keys (SHA-256 hashed at rest)
- `app/sync/` — durable queue, worker, processor, stale/DLQ lifecycle
- `app/crawler/` + `app/knowledge/` — SSRF-guarded crawler, chunker,
  keyword + optional vector search
- `alembic/versions/` — 40+ ordered migrations (single head)
- `frontend/chat/` + `app/static/widget.js` — customer-facing UIs
- `tests/` — pytest suite; `tests/e2e/` — live end-to-end scripts

## Authentication model (do not mix these)

- **Merchant dashboard** — `Authorization: Bearer <JWT>` from
  `POST /v1/auth/signup|login`. Inbox pages additionally use an HttpOnly
  cookie + CSRF header. A merchant chatting inside their own dashboard
  does **not** need a customer conversation token.
- **Public customer chat** — `x-api-key: pk_live_…` only. The first
  `POST /v1/chat` returns a `conversation_token`; every later request on
  that conversation must also send `x-conversation-token`. Tokens are
  per-conversation secrets compared with constant-time HMAC.
- Tenant isolation: every store-scoped query filters by `store_id`
  resolved from the credential — never from a request parameter.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # add -r requirements-dev.txt for tests
cp .env.example .env                       # fill DATABASE_URL, REDIS_URL, CREDENTIAL_ENCRYPTION_KEY
alembic upgrade head                       # REQUIRED before first boot (AUTO_CREATE_TABLES=false)
uvicorn app.main:app --reload              # API (+ inline worker) on :8000
```

Postgres needs the `pgvector` extension available (the `pgvector/pgvector:pg16`
image in docker-compose has it); without it the app boots fine and semantic
search degrades to keyword search.

Quick stack alternative: `docker compose up` (postgres, redis, api, worker —
migrations run in the api entrypoint).

## Environment variables that matter

| Variable | Notes |
| --- | --- |
| `DATABASE_URL`, `REDIS_URL` | required |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key — required to encrypt merchant datasource credentials |
| `GROQ_API_KEY_1..14` | optional pool; without keys chat uses deterministic answers |
| `ENVIRONMENT=production` | turns on hard validation: JWT secret ≥32B, no localhost DB/Redis, non-empty CORS, and **refuses `ALLOW_LOCAL_DATASOURCE_HOSTS`** |
| `ALLOW_LOCAL_DATASOURCE_HOSTS` | dev-only SSRF bypass for local fixtures. Refused in production |
| `RUN_SYNC_INLINE` | false whenever a dedicated worker runs |
| `AUTO_CREATE_TABLES` | must be false in production; `alembic upgrade head` is the deploy step |
| `SYNC_QUEUE_CLAIM_IDLE_MS` / `SYNC_QUEUE_LOCK_TTL_MS` | crash-recovery tuning (default 5 min / 10 min) |
| `SYNC_WORKER_CONCURRENCY` / `SYNC_WORKER_POLL_MS` | worker sizing (default 4 / 5000) |

## Database migrations

Change a model in `app/db/models.py`, `app/chat/models.py`,
`app/usage/models.py`, or `app/knowledge/chunk.py`, then:

```bash
alembic revision --autogenerate -m "add stores.timezone"
# READ the generated file before committing (autogenerate drops+adds renames)
alembic upgrade head
```

Existing create_all-era database? `alembic stamp 0001` first. Details in
`alembic/README.md`. `tests/test_migrations.py` fails the build if the
migration history and ORM models drift apart.

## Testing

```bash
# unit + integration (needs local postgres+redis, or they auto-skip):
DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/test_db \
REDIS_URL=redis://127.0.0.1:6379/0 \
CREDENTIAL_ENCRYPTION_KEY=<key> pytest

# live end-to-end (real worker, real redis, deterministic fixtures):
python scripts/dev/live_website_worker_e2e.py
python scripts/dev/live_worker_restart_recovery.py   # kill -9 + reclaim + no duplicates
python scripts/dev/live_idle_redis_worker.py         # 5-minute idle worker health
python scripts/dev/live_tenant_isolation_e2e.py      # cross-merchant negative tests
python tests/e2e/api_smoke_test.py                   # against a running server
python tests/e2e/acceptance_a_to_z.py                # full merchant journey, 30 checks
```

## Deployment

- `render.yaml` — Render blueprint (api service runs migrations in the
  entrypoint and sets `RUN_SYNC_INLINE=false`; separate worker service).
- `docker-compose.prod.yml` — api + worker + postgres + redis + caddy.
- Production checklist: `ENVIRONMENT=production`, strong `JWT_SECRET_KEY`,
  `AUTO_CREATE_TABLES=false`, `RUN_SYNC_INLINE=false`, migrations as a
  deploy step, `ALLOW_LOCAL_DATASOURCE_HOSTS` unset.
- Single-instance note: `STORAGE_BACKEND=local` chat images live on one
  disk — move to S3 (vars are ready) before scaling to multiple API
  instances.

See `DEPLOY.md` for the full runbook and `LAUNCH_READINESS_REPORT.md`
for the pre-launch status.
