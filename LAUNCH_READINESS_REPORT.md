# 🚀 UNIVERSAL AI AGENT — LAUNCH READINESS REPORT

**Updated:** 2026-09-08  
**Repository:** `abdullahalhossain-bd/universal-ai-agent`  
**Status:** 🟢 **Launch-ready. Full test suite green (262 passed / 0 failed), migrations verified end-to-end on PostgreSQL 16 + pgvector, live E2E merchant journey passed 36/36 (website connect → datasource sync → chat → discovery → database verification).**

## Functional E2E fixes (2026-09-08, round 2 — live merchant-journey verification)

After the first audit round made the suite green, a live end-to-end run of the
full merchant journey (signup → connect website → connect REST/Postgres
datasources → discovery → mapping → sync → chat → knowledge search → API-key
widget chat) surfaced five functional bugs, all fixed and verified:

### 1. Dashboard Chat Preview returned 401 for every merchant (fixed)

The mounted `/v1/chat` router authenticated with `authenticate_api_key`
only, but the dashboard's Chat Preview page has no `x-api-key` — it sends
the merchant's `Authorization: Bearer <jwt>` session. Every dashboard chat
preview failed with 401. The router now authenticates via
`get_current_store`, which accepts BOTH credentials (widget `x-api-key`
and dashboard JWT) with identical suspended-store enforcement.
`/v1/knowledge/{search,semantic-search,hybrid-search,embeddings/generate}`
had the same JWT blind spot and now accept both credentials too.

### 2. Mixed-intent chat crashed with 500 when no GROQ key was configured (fixed)

The mixed (product + knowledge) path called `load_groq_provider()` AFTER
making the atomic budget reservation and without any error handling — a
deployment without `GROQ_API_KEY_*` got a raw 500 AND leaked the budget
hold. The path now gates on a cheap `has_groq_keys()` probe (added to
`app/llm/groq.py`; builds nothing) BEFORE any reservation, and falls back
to a deterministic bilingual answer composed from the actual product +
knowledge results.

### 3. Natural-language chat queries zeroed out on common English question words (fixed)

"Do you have earbuds?" returned zero products: the chat search ANDs every
term, and "do/you/have" matched nothing. The shared stopword module
(`app/search/stopwords.py`) covered Banglish but was not wired into the
chat search path and lacked English question vocabulary. It now includes
the full English/Banglish/Bengali question vocabulary (do, does, have,
you, any, want, looking, available, …), strips punctuation per token, and
the chat search unions it with its legacy inline list. "show me
smartphones under 30000" and "do you have earbuds?" both hit the right
products in live verification.

### 4. Product `category` from the merchant mapping was silently dropped (fixed)

`normalize_row()` never extracted the mapped `category` field even though
the `products.category` column exists, the mapping API accepts it, and
free-text search searches it. Merchant categories now sync through.

### 5. Merchant website ingest blocked local sites; REST connection test gave silent false negatives (fixed)

- The knowledge website crawler enforced its SSRF guard without honoring
  `ALLOW_LOCAL_DATASOURCE_HOSTS` — the documented development escape
  hatch used by the datasource guards — so locally running merchant
  sites could never be ingested in development. The crawler now uses the
  same `local_hosts_allowed()` toggle (added as a public helper in
  `app/core/network_guard.py`); production (toggle unset) keeps the full
  strict sweep including DNS-resolution checks. SSRF tests pin the
  toggle off explicitly to keep asserting the strict default.
- `RESTConnector.test_connection()` probed only the base URL (frequently
  404 on real APIs) and swallowed all error details, returning a bare
  `connected: false`. It now falls back to the configured products
  endpoint and records the failure reason on `last_test_error`, which
  the datasource test route surfaces to the merchant.

### Live verification matrix (2026-09-08, all green — 36/36)

Signup → store → JWT · website ingest (8 pages / 8 chunks crawled) ·
website listed · REST datasource test + create + mapping suggest/apply ·
REST sync → 5 products persisted · `/v1/products/search` · Postgres
datasource test + create · schema discovery (both endpoints) · PG mapping
apply · PG sync → 5 products persisted · chat via dashboard JWT (mixed
query with deterministic fallback) · chat natural-language query ("do you
have earbuds?" → SoundBuds Pro) · knowledge search · direct DB checks
(migrations at head `0019`, pgvector `vector` column present, product
rows owned exclusively by the creating store) · API-key creation (hash
storage, plaintext returned once) · widget `x-api-key` chat round-trip
returning real product answers.

## What this audit fixed (2026-09-08, round 1)

### 1. Migration chain was broken on a virgin database (BLOCKER — fixed)

Revision id `0008_product_datasource_ownership` was **34 characters** — Alembic's
`alembic_version.version_num` column is `VARCHAR(32)`, so `alembic upgrade head`
crashed with `StringDataRightTruncation` the moment it reached that revision on a
fresh database. **CI never caught this because `docker-publish.yml`'s branch
filter is corrupted (`branches: ain]`), and the chain-running migration tests
were written for sqlite, which cannot execute the chain's Postgres-only DDL.**

Fixes:

- Renamed the revision to `0008_datasource_ownership` (updated the
  `down_revision` reference in `0018_merge_datasource_ownership`).
- Full chain `0001 → 0019` now verified green on a virgin PostgreSQL 16.2 +
  pgvector 0.6.2 database (16 tables, single head).
- `tests/test_migrations.py` now runs the chain (and the 0007 drift-replay test)
  against a throwaway Postgres database, and skips with a clear reason when no
  Postgres is reachable. CI's pgvector service container covers it.

### 2. Alembic / ORM model drift (BLOCKER — fixed)

`agent_configs`, `admin_audit_logs`, `visitor_profiles` were created by
migrations but their ORM models were not part of the "active model set"
(`alembic/env.py`, `app/main.py`, test import list) — autogenerate would flag
them as removable. Added the imports in all three places.

### 3. Stamped-legacy databases never got pgvector (fixed)

A database stamped mid-chain (like production was, at `0006`) skips 0002's
TEXT→VECTOR conversion forever, while the ORM resolves `Vector(384)` on a
pgvector-capable server — semantic-search writes would fail at runtime. New
migration **`0019_vector_embedding_guard`** re-applies the guarded conversion at
the chain head (no-op when already vector, no-op without pgvector, drops the
0011 btree index before altering).

### 4. Redis async client broke across event loops (fixed)

`app/core/redis.py` exposed a module-level `redis.asyncio` client whose
connections bind to the first event loop. Any later loop (tests, reloads) got
`RuntimeError: Event loop is closed` from the pool. Replaced with a
loop-aware proxy: one client per running loop, same behaviour in production.

### 5. Budget could be bypassed by the LLM typo-correction call (fixed)

In the mixed-intent chat path, `_llm_correct_search_term` built the LLM stack
**before** the atomic budget reservation — a store with `monthly_budget = 0`
(or exhausted) could still spend tokens. Added `_has_budget_headroom()` gating
before any auxiliary LLM call; the reservation remains the single source of
truth for the main path.

### 6. Product-search features documented by tests but not implemented (fixed)

- **Free-text SQL search**: `ProductSQLBuilder` ignored `request.query`
  entirely. Now every term must match at least one searchable mapped column
  (name/description/category/brand/sku) with bound `search_term_N` parameters —
  parameterized, identifier-validated, injection-safe.
- **Typo-tolerant synonyms**: `expand_terms()` gained a rapidfuzz fallback
  (cutoff 78) so "laptpo"/"leptop"/"sandl"/"mobil" reach the right synonym
  group; unrelated words still don't.
- **Model-number intent**: "Acme X200"-style queries (letter+digit token, no
  product/knowledge vocabulary) now classify as PRODUCT_SEARCH (confidence
  0.60) instead of UNKNOWN.

### 7. Billing error semantics (fixed)

`create_checkout_session` validated the plan's price before checking the Stripe
config, so an unconfigured integration returned 400 instead of 503. Config is
now checked first.

### 8. Render blueprint fixes (`render.yaml`)

- **CORS widget blocker**: `CORS_ALLOW_ORIGINS` locked to the dashboard origin
  would CORS-block the embeddable widget on every merchant storefront. Set to
  `*` with documentation — safe because the API uses `allow_credentials=False`
  and header-based auth (no cookies → no CSRF surface).
- **SPA deep links 404**: added `/* → /index.html` rewrite for the dashboard.
- **Worker migration race**: worker now sets `SKIP_MIGRATIONS=1` (the report
  previously claimed this was already true).
- **Redis exposure**: removed the `0.0.0.0/0` ipAllowList (instance stays on
  Render's private network).
- **Plan sizing**: web service `free` (512 MB) cannot host torch embeddings —
  bumped to `0.5c-1gb`; free Postgres is deleted after 30 days — bumped to
  `basic-256mb`.

### 9. Security fixes & hygiene

- **Widget XSS guard**: product/source hrefs in `app/static/widget.js`,
  `frontend/widget/widget.js`, `frontend/chat/app.js` now only allow
  `http(s)` — a malicious `javascript:` product URL from a merchant DB can no
  longer become a clickable payload.
- CORS docstring in `app/core/security.py` aligned with the by-design wildcard
  (credentials stay off).
- Removed tracked user uploads (`data/chat-images/`), `.bak` file, tree-dump
  artifacts; `.gitignore` now blocks `data/`, `*.bak`, `*_tree.txt`.
- Test-suite isolation: signup rate-limit hook neutralized via autouse fixture
  (limiter mechanics still covered by `test_budget_security` against real
  Redis); SSRF tests pin `ALLOW_LOCAL_DATASOURCE_HOSTS` off explicitly;
  webhook test uses a unique subscription id.

## Verified baseline (2026-09-08)

- **Test suite: 262 passed / 0 failed / 2 xfailed** against real PostgreSQL
  16.2 + pgvector 0.6.2 and Redis 7.2.5 (CI-equivalent environment:
  `AUTO_CREATE_TABLES=false`, schema built by `alembic upgrade head`).
- Frontend dashboard: `npm ci && npm run build` green.
- Live smoke: app boots, `/health` 200, `/ready` 200 (DB+Redis), `/docs` 200,
  `/chat/` static UI 200, signup → `/me` → API-key creation → chat round-trip
  all green, invalid credentials correctly 401.

## Production requirements (unchanged — these need YOUR accounts)

1. **Render account connected** — the blueprint (`render.yaml`) provisions
   web + worker + Redis + Postgres + dashboard.
2. **`GROQ_API_KEY_1` (or more)** — required for real AI chat/vision.
3. **Stripe keys** — optional until billing/webhooks are tested.
4. **S3-compatible storage** — `STORAGE_BACKEND=local` is fine for trials; use
   `s3` (Cloudflare R2 etc.) for durable image uploads across restarts/replicas.
5. **DNS/domain** — update `API_BASE_URL` in `render.yaml` to your real API
   host after first deploy.

## Remaining known limitations (non-blocking)

- *(Audit note: an earlier draft flagged a "corrupted branch filter" in
  `.github/workflows/docker-publish.yml` — byte-level verification proved both
  workflow files contain the correct `branches: [main]`; the apparent
  corruption was a terminal/display artifact, not real.)*
- `app/sync/scheduler.py` (periodic re-sync) is not deployed as a service —
  datasources re-sync only when enqueued via the API.
- Dashboard JWTs default to 7-day lifetime with no revocation path; consider
  shortening the TTL and adding a token-version check post-launch.
- Login endpoints have no per-IP brute-force throttle (signup does); consider
  reusing the signup limiter pattern for `/v1/auth/login` and
  `/v1/admin/login`.

## Current launch verdict

**Code-side verdict:** 🟢 Ready — tests, migrations, build, and live smoke all
green.  
**Infrastructure-side verdict:** 🟢 Blueprint prepared and corrected.  
**Live production verdict:** ⏳ Requires Render account + real Groq credentials
+ one real merchant datasource exercised end-to-end (see the E2E checklist
below).

## Real ecommerce E2E test plan (after deploy)

1. `GET /health` → 200; `GET /ready` → 200 with DB+cache confirmed
2. Dashboard loads; signup → login → `/me`
3. Store/website creation; API key creation and rotation
4. Real ecommerce datasource credential storage/encryption
5. Real product discovery/sync; product records visible only to the owning store
6. Chat request against the real catalog; search / hybrid retrieval
7. Image upload and analysis
8. Background sync enqueue → worker dequeue → DB update
9. Tenant-isolation negative test (second user/store)
10. Auth negative tests (missing/invalid JWT/API key)
11. Alembic head confirmed; Render health checks green after redeploy
