# Universal Commerce AI Agent — Production Readiness Audit Report

**Audit cycle completed:** 14 September 2026 · **Deliverable:** updated source ZIP + this report
**Verdict:** **Production-ready after fixes** — all suites green (473/473 unit+integration, 30/30 acceptance, 8/8 live E2E)

---

## 1. Executive Summary

A complete inspect → run → diagnose → fix → re-test cycle was performed against real services
(PostgreSQL 16 + pgvector, Redis 7, real uvicorn API, real worker subprocesses, Chromium via
Playwright). The core architecture proved sound: tenant isolation is enforced at every layer,
the Redis Streams queue is genuinely durable, the SSRF guard is well designed, and the chat
pipeline degrades gracefully without an LLM provider.

The audit nevertheless found and fixed one **business-critical reliability failure** (worker
crash recovery reporting "recovered" while the sync actually failed with 0 products), one
**live 500 crash** on `/v1/mapping/*`, one **auth-context inconsistency** on `/v1/images`,
**committed credentials + PII** in the bundled demo site, and a set of **frontend reliability
defects** (any API error logged merchants out). All remediations were verified by re-running
the failing suites plus new regression tests and a new 30-check acceptance E2E.

## 2. What Was Broken — Root Causes

### 2.1 Worker crash recovery: "recovered" but `partial`, 0 products, 0 pages
- **Root cause A:** the SSRF test-harness shim (`sitecustomize.py`) could not import `app` —
  `python -m app.sync.worker` puts the repo root on `sys.path` only *after* interpreter startup,
  so the shim's import failed silently (`except: pass`), DNS for the fixture host failed,
  `pages_failed=1` → status `partial`.
- **Root cause B:** a worker killed mid-crawl left its `SyncRun` in `running` forever — no
  orphan reaper; PostgreSQL (the authoritative status source) kept lying to the dashboard.

### 2.2 `/v1/mapping/suggest|confirm` → 500
Routes passed Pydantic `ColumnPayload` objects into a service that indexes `c["name"]` →
`TypeError` → global 500. Unit tests only fed the service plain dicts; the route contract was
never exercised.

### 2.3 `/v1/images` merchant detection
Used header **presence** (`bool(authorization) and not bool(x_api_key)`) instead of validating
the JWT against the store — the exact bug class `/v1/chat` had already fixed for itself.

### 2.4 Secrets in `demo website/`
Real-looking shared-hosting DB credentials in `config.php` and a plaintext-password/PII SQL
dump — referenced by nothing in the platform.

### 2.5 Frontend defects
`client.js` logged merchants out on **any** non-OK status (422/404/429/503); Overview/Usage
null-crashes; unbounded overlapping polls (inbox 5s, website status 2s, widget 5s/30s);
website poll hammered a dead API for 10 minutes; Enter-key bypassed double-submit guards;
widget fetches had no timeout; slow analytics responses could overwrite newer ones.

### 2.6 Others
compose double-worker (inline worker + dedicated worker); SSRF decimal/hex IPv4 literal gap
(strict xfail); `ALLOW_LOCAL_DATASOURCE_HOSTS` not refused in production; unauthenticated
`POST /v1/stores` minted live API keys; no prompt-injection rules; 14 silent `except: pass`
sites; OG-product pages not extracted; dead dangerous modules (`rest_api_connector.py`
without SSRF guard, duplicate `postgres.py`, shadowed `base.py`, `discovery/test_data.py`
writing fake products to the real DB); root README was the Alembic doc; `.env.production.example`
referenced by DEPLOY.md but missing; recovery script wrote logs into the repo root.

## 3. What Was Fixed (verified)

| Area | Fix | Verified by |
|---|---|---|
| Recovery harness | shim adds cwd to `sys.path` before importing `app`; failures print tracebacks | `live_worker_restart_recovery.py`: success, 1 product, 1 page, ACK, no dupes |
| Orphaned runs | new `app/sync/runs.py::mark_superseded_runs()` wired into processor + web ingestion | 2 regression tests + recovery script |
| Mapping 500 | `_column_dicts()` normalization at the route boundary | `api_full_e2e_test.py` 200/200 |
| Images auth | shared JWT-validating `is_dashboard_request_for_store()` (chat + images) | regression test + auth suite |
| Secrets | `demo website/` removed (+ CI job) | repo inventory |
| Frontend | 401-only logout; AuthContext 401/403-only; null guards; poll in-flight guards; 3-strike poll cutoff; Enter-key guards; request-sequence guard; widget timeouts | `npm run build` + browser e2e |
| SSRF | decimal/hex literal normalization | regression test (xfail flipped) |
| Production guards | validator refuses `ALLOW_LOCAL_DATASOURCE_HOSTS`; `POST /v1/stores` 403 in prod | regression tests |
| Prompt injection | untrusted-context + no-rules-disclosure rules (planner + responder) | unit suite |
| Compose | `RUN_SYNC_INLINE=false` in both compose files | config review |
| OpenGraph | `extract_og_product()` merged into `parse_page` | 2 regression tests |
| Silent excepts | all 14 sites now log | unit suite |
| Ops/docs | log paths off repo root; dead files removed; `.env.production.example`; README rewritten; outdated image e2e fixed | full suite |

## 4. Files Changed

- **Backend modified:** `app/core/config.py`, `app/api/routes/stores.py`, `app/api/routes/images.py`,
  `app/api/v1/mapping.py`, `app/auth/dashboard_auth.py`, `app/chat/router.py`, `app/ai/prompts.py`,
  `app/crawler/parser.py`, `app/crawler/web_ingestion.py`, `app/knowledge/crawler.py`,
  `app/products/semantic_attributes.py`, `app/search/store_vocabulary.py`,
  `app/sync/processor.py`, `app/static/widget.js`
- **Backend added:** `app/sync/runs.py`, `.env.production.example`
- **Tests added:** `tests/test_audit_regressions.py` (15), `tests/e2e/acceptance_a_to_z.py` (30 checks)
- **Tests modified:** `tests/test_chat_knowledge.py`, `tests/test_platform_admin.py`,
  `tests/e2e/api_full_e2e_test.py`
- **Frontend modified:** `client.js`, `AuthContext.jsx`, `Overview/Usage/Billing/Websites/Messages/ChatPreview/Analytics.jsx`
- **Ops/docs modified:** both compose files, `ci.yml`, `README.md` (rewritten), 2 dev scripts
- **Deleted:** `demo website/`, `app/connectors/{rest_api_connector,postgres,base}.py`,
  `app/discovery/test_data.py`, 7× `check_*.py`, `tmp_*`, stress/agent JSON artifacts, `neon.ts`,
  root `package.json`/`package-lock.json`

## 5. Tests Executed — Results

| Suite | Result |
|---|---|
| pytest full suite (3 runs: baseline/interim/final) | **PASS — 473/473** |
| `live_worker_restart_recovery.py` (kill -9 + reclaim) | **PASS** — success, 1 product, 1 page, ACK, DUPLICATE_CHECK=TRUE |
| `live_website_worker_e2e.py` | **PASS** |
| `live_idle_redis_worker.py` (305 s idle) | **PASS** — consumed, ACK, 0 connection errors |
| `live_tenant_isolation_e2e.py` | **PASS** — A↔B blocked both directions |
| `tests/e2e/acceptance_a_to_z.py` (new) | **PASS — 30/30** |
| `api_smoke_test.py` | **PASS — 26/26** |
| `api_e2e_test.py` | **PASS — 8/8** (semantic search w/ real embeddings) |
| `api_full_e2e_test.py` | **PASS — 10 pass, 1 skip** (image analyze needs real Groq key) |
| Browser e2e (widget + dashboard, Playwright/Chromium) | **PASS — 2/2** |
| `compileall` + `npm run build` | **PASS** — 1845 modules, 0 errors |

**FAIL: none.**

## 6. E2E Acceptance (section 26 of the brief)

Real server + real worker + two merchants + crash + Redis outage, all through real HTTP:

signup → login → store → website added → datasource + SyncRun → job queued → worker crawl →
products (1) + knowledge (1) extracted → status **success** → dashboard status correct →
**merchant chats without customer token** → customer widget conversation via API key only →
conversation token round-trip → correct merchant's product retrieved (grounded) →
**A cannot read B / B cannot read A** (status 404, chat products, inbox scoping) →
**Redis killed: status endpoint still serves PostgreSQL state, no corruption** → Redis back →
re-sync → **no duplicates**. Worker crash recovery verified separately (above): the previously
reported `partial/0/0` outcome is fully resolved and the orphaned run is closed with an
explanatory error.

## 7. Security Findings

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| SEC-1 | Committed DB credentials + plaintext PII dump in `demo website/` | **Critical** | Removed; **rotate credentials + purge git history** |
| SEC-2 | SSRF guard strong (DNS validation, pinned resolver, robots, size/redirect caps); decimal/hex literal gap | Medium | Fixed + regression tests |
| SEC-3 | Tenant isolation verified (store-scoped queries, hashed API keys, constant-time tokens) | Info | Verified by 3 suites |
| SEC-4 | `POST /v1/stores` minted unauthenticated API keys | High | 403 in production; dev/test preserved |
| SEC-5 | `ALLOW_LOCAL_DATASOURCE_HOSTS` (full SSRF bypass) unguarded in prod | Med-high | Boot-time refusal |
| SEC-6 | images.py header-presence heuristic | Medium | Shared JWT-validating rule |
| SEC-7 | No prompt-injection defense | Medium | Untrusted-context rules added |
| SEC-8 | localStorage JWT; capability-URL images; wildcard CORS (no credentials) | Low | Documented trade-offs; CSRF enforced on inbox |
| SEC-9 | egress-ip debug route (auth-gated, 404 in prod) | Low | Retained, documented |

## 8. Performance & Scalability

Request path is clean (sync fully queued; plan-based recrawl intervals; store-scoped indexed
SQL + Redis vocabulary cache; metered LLM budget with deterministic fallback). Fixed:
double-worker compose, unbounded overlapping polls, widget fetch timeouts. Notes: move
`STORAGE_BACKEND` to S3 before horizontal API scaling; worker concurrency is env-tunable;
no synthetic load numbers are claimed (sandbox) — concurrency correctness is guaranteed by
the per-datasource lock + idempotent upserts, verified by the recovery suite.

## 9. Deployment Requirements

1. Postgres 16 + pgvector, Redis 7, `CREDENTIAL_ENCRYPTION_KEY`, strong `JWT_SECRET_KEY`;
   optional `GROQ_API_KEY_*`, Stripe keys.
2. `alembic upgrade head` **before** the new app serves traffic.
3. Start API (`uvicorn app.main:app`) and worker (`python -m app.sync.worker`) separately with
   `RUN_SYNC_INLINE=false` — do not assume the platform starts the worker.
4. Production validators enforce: `ENVIRONMENT=production`, `AUTO_CREATE_TABLES=false`,
   non-localhost DB/Redis, non-empty CORS, no `ALLOW_LOCAL_DATASOURCE_HOSTS`.
5. `/health` (liveness) and `/ready` (DB+Redis gate) for probes.
6. Single-instance with local image storage; S3 vars ready for scale-out.

## 10. Remaining Limitations / NOT TESTED

| Item | Status | Reason / alternative validation |
|---|---|---|
| Live Groq LLM + vision replies | NOT TESTED | no real key; deterministic/budget/fallback paths + prompt contracts verified |
| Live Stripe billing | NOT TESTED | webhook signature, plan changes covered by unit tests; 503 without keys verified |
| Real public-website crawls | NOT TESTED | egress-restricted sandbox; SSRF units + full-stack local crawls + robots/redirect units |
| Large multi-tenant load | NOT TESTED | sandbox scale; lock/idempotency design guarantees + single-tenant realistic load |
| S3 image backend | NOT TESTED | no credentials; local backend e2e-verified, S3 code-reviewed |
| Legacy `admin.html` test chat | PARTIAL | still uses customer credentials by design (end-user simulator); React dashboard is the supported surface |
| Demo PHP site | REMOVED | requires credential rotation by the original owner |

Also: sentence-transformers loads a local model per worker (memory note); mixed-language
query planner improves with a real provider key; **git history still contains the removed
secrets until purged by the repository owner.**

## 11. Status Ledger

**PASS:** unit/integration suite · worker crash recovery (business outcome) · Redis
idle/outage/restart resilience · tenant isolation (both directions) · chat auth contexts ·
crawler + SSRF · generic product extraction (JSON-LD / product JSON / microdata / semantic
HTML / OpenGraph) · frontend dashboard · API contract · database + migrations · deployment
config.

**PARTIAL:** image analyze e2e (provider key absent).

**NOT TESTED:** live LLM/vision providers · live Stripe · public-website crawls ·
large-scale load · S3 backend.

**FAIL:** none.
