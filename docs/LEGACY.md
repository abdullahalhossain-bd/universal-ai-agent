# Legacy Code Isolation Map

Runtime evidence-based (2026-08-28): the table below records which
packages participate in the running application's import graph
(`import app.main` → uvicorn boot) and which do not. Nothing in the
"not loaded" column is reachable from any mounted route.

Kept rather than deleted deliberately: several original test files
(`tests/test_mapping_engine.py`, `tests/test_schema_analyzer.py`)
still exercise connector/service modules, and wholesale deletion of
16 packages in one pass is exactly the kind of irreversible change
this hardening effort avoids. Quarantine-by-documentation today;
physical removal can follow once those tests are re-pointed or
retired.

## Active surface (loaded at boot)

| Package | Role |
|---|---|
| `app.main` | FastAPI entrypoint (chat, stores, products, knowledge, health) |
| `app.api.routes.{stores,products}` | Mounted `/v1/stores`, `/v1/products` |
| `app.api.v1.knowledge` | Mounted `/v1/knowledge/*` |
| `app.chat` | Router, ChatService, response stack |
| `app.core` | config, security, rate_limit, redis, tenant |
| `app.db` | database.py (engine/Base), models.py |
| `app.auth` | dependency.py (chat/knowledge), api_key.py (stores/products) |
| `app.knowledge` | crawler, chunk, search, service, vector_* |
| `app.llm` | LLMProvider base, GroqProvider |
| `app.ai` | ACTIVE SUBSET ONLY — see below |
| `app.planner`, `app.search` | Query planning, text search |
| `app.usage` | UsageRecord model, budget repository |

## app.ai active subset

Only these modules are imported at boot:
`context_formatter`, `cost_engine`, `prompts`, `provider_router`,
`response_generator`, `response_policy`, `template_response`.

The remaining files in `app/ai/` are pre-refactor leftovers and are
NOT loaded.

## Legacy surface (NOT loaded at boot, not mounted)

| Package / file | Status | Note |
|---|---|---|
| `app.connectors` | **ACTIVE** | merchant datasource connectors (postgres/mysql/rest/website) used by the sync worker + datasource service. Legacy leftovers inside it (unified_product, normalizer, CircuitBreaker, RestApiConnector, registry) remain dead. |
| `app.sync` | **ACTIVE** | Redis Streams queue, worker, processor, upsert, DLQ, scheduler — the product/website/embeddings job pipeline. |
| `app.crawler` | **ACTIVE** | `crawler/web_ingestion.py` is the `website_sync` executor (`app.crawler.parser`/`sitemap` are used by `app.knowledge.crawler`). |
| `app.discovery` | **ACTIVE** | `SQLSchemaScanner` + mapping engine power `/v1/discovery/scan` and datasource discovery. |
| `app.images` | **ACTIVE** | chat image upload/verification (`app.api.routes.images`/`media`). |
| `app.catalog` | dead | superseded by Product pipeline |
| `app.domain` | dead | early domain-model draft |
| `app.models` | dead (not broken) | thin re-export shims around `app.db.models`; kept for legacy-test compatibility |
| `app.products` | mostly dead | `attribute_filters`, `semantic_attributes`, `sql_identifier`, `recommendation` are ACTIVE (chat/search); `service.py`, `query_service.py`, `sql_builder*.py` are unreferenced by the boot graph |
| `app.query` | dead | superseded by planner/search stack |
| `app.query_engine` | partially dead | only `tools.stock_tool` (and its `tools.base`) load via `app.chat`; the rest is unwired |
| `app.responses` | dead | superseded by `app.chat.response_*` |
| `app.schemas` | **ACTIVE (minimal)** | only `schemas/product.py` (UniversalProduct) is imported (connectors) |
| `app.services` | dead in app | product_sync/query_engine helpers; nothing in the boot graph imports them |
| `app.tenants` | dead (not broken) | pre-store multi-tenancy draft |
| `app.vision` | **ACTIVE** | wired through the chat vision flow (vision_router/vision_service) |
| `app.workers` | never existed / dead | — |
| `app.db.session.py` | duplicate | only legacy code imports it; use `app.db.database` |
| `app.db.init_db.py` | dead | legacy bootstrap, imports app.db.session |
| `app/api/v1/{chat,connectors,discovery,mapping,products,router}.py` | not mounted | the aggregate `router.py` is NOT included in `app.main`; `discovery.py`, `mapping.py`, `knowledge.py` are mounted individually with the `/v1` prefix. `connectors.py` (`POST /connectors/test`) is authenticated + SSRF-guarded in case it is ever mounted. |

> NOTE (2026-09 audit): the table above originally claimed `app.sync`,
> `app.crawler`, `app.images`, `app.discovery` and `app.connectors` were
> dead. Runtime import verification (`import app.main`) proves they are
> all loaded and live — the datasources/websites/ingestion feature set
> depends on them. See worklog/audit report for details.

## Rules going forward

1. New code must import from the active surface only.
2. Do not import legacy packages from active code — it would
   re-couple the boot graph to unmaintained modules.
3. Removing a legacy package requires first re-pointing or
   retiring the two legacy test files that reference
   `app.connectors` / `app.services`.
