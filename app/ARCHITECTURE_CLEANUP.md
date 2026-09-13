# Architecture Cleanup & Completion Status

## Completed in this pass

### 1. Mapping Confirmation System (production-ready)
- **File**: `app/connectors/mapping_confirmation.py`
- **API**: `app/api/v1/mapping.py`
  - `POST /mapping/suggest` — discovery + confidence buckets
  - `POST /mapping/confirm` — merchant accepts/overrides
  - `POST /mapping/apply` — persist onto datasource

Confidence rules:
| Confidence | Action |
|------------|--------|
| >= 0.90 (critical fields >= 0.95) | Auto accept |
| 0.70 – 0.89 | Ask merchant |
| < 0.70 | Manual mapping |

### 2. Real-time Stock Tool
- **File**: `app/query_engine/tools/stock_tool.py`
- `StockService` with freshness window (default 5 min)
- Sources: `cache` | `cache_stale` | `unavailable`
- Never invents stock numbers
- Binds to DB session via `bind_db()`

### 3. Discovery API (merchant DB)
- **File**: `app/api/v1/discovery.py`
- Accepts merchant `connection_url` (not only app DB)
- Basic SSRF block for localhost / metadata hosts
- Optional table focus → attaches mapping confirmation

### 4. Query-engine tools: product_search & knowledge_search (wired)
- **Files**: `app/query_engine/tools/product_search.py`, `app/query_engine/tools/knowledge_search.py`, `app/query_engine/executor.py`
- `product_search` now queries the real synced `products` table
  (store-scoped, same synonym expansion as the live chat path);
  requires `bind_db()` — `PlanExecutor.run()` now accepts a `db`
  session and binds it to any tool exposing `bind_db` (this also
  fixes `StockTool`, which had the same gap and was silently unusable
  even though its own logic was complete).
- `knowledge_search` now delegates to the same `KnowledgeSearchEngine`
  the live chat path uses.
- `image_analysis` is **still a stub, deliberately** — there is no
  persisted `ImageRecord` lookup and `VisionRouter` itself is 100%
  unimplemented; wiring this tool to it would just relay one stub
  into another. See the module docstring in
  `app/query_engine/tools/image_analysis.py` for the actual
  prerequisites.
- Tests: `tests/test_query_engine_tools.py`.

---

## Duplicate systems (cleanup targets — do not add features here)

| Keep | Deprecate / merge into |
|------|------------------------|
| `app/planner/rule_planner.py` (used by chat) | `app/ai/planner.py`, `app/query_engine/planner.py` |
| `app/chat/service.py` (runtime) | Gradually extract tools into `query_engine/tools` |
| `app/sync/service.py` ProductSyncService | `app/catalog/sync_service.py` (already marked LEGACY) |
| `app/discovery/*` + `mapping_confirmation` | Prefer over pure `connectors/mapping_engine` name-only |
| `app/ai/cost_engine.py` + usage_repo | Keep; enforce before every LLM call |

## Recommended next order

1. Wire `StockTool` into chat `_is_stock_question` path (optional force_live)
2. Unify intent: single `Intent` enum used by planner + query_engine + chat
3. ~~Extract product search from chat.service into `query_engine/tools/product_search.py`~~ done — see item 4 above
4. Semantic cache integration in chat handle (non-stock answers only)
5. Embeddable widget + merchant dashboard (frontend)

## Do NOT add right now
- New connectors (Shopify etc.)
- Billing Stripe integration
- Full admin dashboard UI
- More LLM providers

Focus: integrate what exists → production reliability.
