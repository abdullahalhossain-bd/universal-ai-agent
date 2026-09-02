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
| `app.catalog` | dead | superseded by Product pipeline |
| `app.connectors` | dead in app | kept alive ONLY by 2 legacy test files |
| `app.crawler` | dead | superseded by `app.knowledge.crawler` |
| `app.discovery` | dead | old website analysis prototype |
| `app.domain` | dead | early domain-model draft |
| `app.images` | dead | unused image handling |
| `app.models` | dead + broken | imports non-existent `app.core.database` |
| `app.products` | dead | superseded by `app.api.routes.products` |
| `app.query` | dead | superseded by planner/search stack |
| `app.query_engine` | dead | old tool-based engine |
| `app.responses` | dead | superseded by `app.chat.response_*` |
| `app.schemas` | dead | superseded by per-module schemas |
| `app.services` | dead in app | product_sync/query_engine helpers, only legacy tests reference |
| `app.sync` | dead | old catalog sync |
| `app.tenants` | dead + broken | pre-store multi-tenancy draft |
| `app.vision`, `app.workers` | dead | never wired |
| `app.db.session.py` | duplicate | only legacy code imports it; use `app.db.database` |
| `app.db.init_db.py` | dead | legacy bootstrap, imports app.db.session |
| `app/api/v1/{chat,connectors,discovery,mapping,products,router}.py` | dead | not included in `app.main` routers; only `knowledge.py` is mounted |

## Rules going forward

1. New code must import from the active surface only.
2. Do not import legacy packages from active code — it would
   re-couple the boot graph to unmaintained modules.
3. Removing a legacy package requires first re-pointing or
   retiring the two legacy test files that reference
   `app.connectors` / `app.services`.
