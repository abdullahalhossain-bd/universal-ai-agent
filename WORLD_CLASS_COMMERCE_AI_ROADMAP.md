# World-Class Commerce AI SaaS Roadmap

## Product Goal

Turn Universal AI Agent from a strong ecommerce chat API into a production-grade, multi-tenant Commerce AI platform that can understand a merchant's catalog and website, hold context-rich conversations, recommend products, execute commerce actions, and provide measurable sales/support intelligence.

## Current Architecture Strengths

The repository already has dedicated layers for chat, planning, AI providers, catalog/data sources, knowledge search, stock lookup, usage, billing, authentication, connectors, and a Redis-backed worker. Conversation history and product context are already persisted, and the planner already supports product search, knowledge search, mixed queries, and catalog browsing.

## Execution Order

### Phase 0 — Stabilize the foundation (P0)

**Goal:** eliminate correctness regressions before adding major features.

- Fix and regression-test planner edge cases, especially Bangla/Banglish existence phrases (`ase`, `ache`) versus explicit stock intent.
- Keep `CATALOG_BROWSE` consistent across planner models and planner implementation.
- Add multilingual planner tests for product/category/name/brand/budget/stock/reference queries.
- Add normalization fixtures for diverse merchant schemas and image/image-gallery formats.
- Verify product context survives follow-ups and pagination.
- Make frontend widget and served `app/static/widget.js` use one canonical source.
- Establish a deterministic test matrix for every commerce intent.

**Exit criteria:** no known P0 planner/normalization regression; CI passes; critical chat flows have automated coverage.

---

### Phase 1 — Conversation Intelligence (P0)

**Goal:** make the assistant understand conversations, not isolated messages.

Build a dedicated conversation state layer containing:

- active product/result set
- selected product
- previous filters
- current category/brand
- budget constraints
- language preference
- unresolved user intent
- pagination position

Support references such as:

- `eta`, `otar`, `oi ta`
- `2nd ta`, `প্রথমটা`, `ওই HP টা`
- `same product`
- `cheaper one`
- `aro dekhao`
- `etar dam koto?`
- `link dao`
- `eta available?`

Use deterministic reference resolution first; only fall back to an LLM when ambiguity remains.

**Exit criteria:** multi-turn product conversations resolve references correctly without requiring the customer to repeat product names.

---

### Phase 2 — Universal Commerce Search (P0)

**Goal:** make arbitrary merchant catalogs searchable through one canonical interface.

Canonical fields:

- id / SKU
- name
- brand
- category
- description
- price / compare-at-price
- currency
- stock / availability
- image / images
- product URL
- attributes / variants
- rating / review count
- tags
- source metadata

Improve automatic schema discovery so a merchant can connect a database/API/CSV and receive a proposed mapping such as:

`title → name`, `sale_price → price`, `qty → stock`, `thumbnail → image`, `link → product_url`.

Add confidence scores and a merchant confirmation step for uncertain mappings.

**Exit criteria:** materially different merchant schemas normalize into the same catalog contract without merchant-specific code.

---

### Phase 3 — Semantic Query Understanding (P0/P1)

**Goal:** understand natural commerce language across English, Bengali, Banglish, and mixed messages.

Extract:

- product/entity
- category
- brand
- budget
- price range
- attributes
- availability
- comparison intent
- recommendation intent
- action intent
- knowledge intent

Examples:

`80k er moddhe gaming laptop chai`

→ category=laptop, use_case=gaming, max_price=80000

`HP er moddhe best ta dekhao`

→ brand=HP, recommendation=true

`eta ki gaming er jonno valo?`

→ reference=current_product, intent=product_evaluation

Do not use hardcoded product examples; all extraction must be generic.

---

### Phase 4 — Recommendation & Ranking Engine (P1)

**Goal:** answer "which one should I buy?" reliably.

Ranking should combine available signals such as:

- query relevance
- explicit customer constraints
- price fit
- stock availability
- attribute match
- rating/reviews when available
- merchant-provided popularity/sales data when available
- business rules

Every recommendation should be explainable:

- why it matches
- strengths
- limitations
- cheaper alternative
- premium alternative

Never invent ratings, sales, specifications, or performance claims that are not present in merchant data.

---

### Phase 5 — Store Knowledge Intelligence (P1)

**Goal:** make the assistant useful beyond products.

Index and retrieve merchant knowledge for:

- shipping
- returns
- refunds
- warranty
- payment methods
- delivery areas
- store address
- opening hours
- FAQs
- policies
- contact information

Route knowledge questions separately from product search and combine both for mixed queries.

Example:

`ei laptop er Dhaka delivery koto din?`

→ product context + shipping knowledge.

---

### Phase 6 — Commerce Actions (P1)

**Goal:** move from chat-to-answer to chat-to-commerce.

Design provider-neutral action interfaces for:

- add to cart
- update quantity
- remove from cart
- checkout URL
- product availability
- order status
- customer lookup (with appropriate authentication)
- wishlist / save for later

Keep actions deterministic and permission-checked. The LLM may propose an action, but backend policy must authorize and execute it.

---

### Phase 7 — SaaS Multi-Tenancy & API Platform (P0/P1)

**Goal:** make it safe to sell to many merchants.

Harden:

- tenant/store isolation
- API key lifecycle
- key scopes
- key rotation/revocation
- rate limiting
- quotas
- usage metering
- request IDs
- structured errors
- audit logging
- webhook authentication
- CORS/security headers

Every request must have an unambiguous authenticated store/tenant context.

**Exit criteria:** automated tests prove cross-tenant catalog, knowledge, conversation, and usage data cannot leak.

---

### Phase 8 — AI Cost & Latency Router (P1)

**Goal:** maximize quality while keeping SaaS gross margin healthy.

Routing strategy:

- greetings / simple deterministic requests → no LLM or cheapest path
- catalog lookup → search/rules first
- simple follow-up → compact model/context
- complex comparison/recommendation → stronger model
- knowledge synthesis → appropriate model with retrieved evidence

Add:

- prompt/context budgets
- response caching where safe
- token/cost estimation
- provider fallback
- timeout/retry policy
- latency tracking

Never trade factual commerce data for a cheaper hallucinated answer.

---

### Phase 9 — Merchant Analytics & AI Insights (P1)

**Goal:** prove business value.

Track:

- conversations
- unique sessions
- search queries
- zero-result queries
- product views/clicks
- recommendation requests
- add-to-cart attempts
- checkout attempts
- conversions when integrated
- response latency
- AI/provider cost
- knowledge gaps

Merchant insights should include actionable summaries such as:

> Customers frequently ask for a product that is not currently in the catalog.

---

### Phase 10 — Developer Experience & Integrations (P1/P2)

**Goal:** make integration take minutes, not days.

Provide:

- one-line widget install
- API quickstart
- OpenAPI documentation
- curl examples
- JavaScript/Python examples
- webhooks
- API key dashboard
- connector health/status

Target integrations:

- custom REST API
- PostgreSQL/MySQL
- CSV/JSON
- Shopify
- WooCommerce
- Magento/Adobe Commerce
- other ecommerce platforms through adapters

---

### Phase 11 — Globalization & Merchant Customization (P2)

Support merchant-level configuration for:

- currency
- locale
- timezone
- language
- brand voice
- greeting
- tone
- product terminology
- business rules

The widget must not assume BDT globally; currency and formatting should come from merchant/product configuration.

---

## Target System Architecture

```text
Merchant DB / API / CSV / Platform
              ↓
       Schema Discovery
              ↓
     Universal Catalog Layer
              ↓
   Search + Knowledge Indexes
              ↓
Customer → Conversation State
              ↓
     Intent / Entity Engine
              ↓
       Commerce Planner
        ↙      ↓       ↘
   Product   Knowledge  Actions
    Search     RAG       API
        ↘      ↓       ↙
       Ranking / Recommendation
              ↓
       LLM Response Layer
              ↓
      Safety + Validation
              ↓
          Customer
              ↓
       Analytics / Events
              ↓
       Merchant Dashboard
```

## Non-Negotiable Quality Rules

1. Never invent price, stock, product specs, ratings, policies, or order information.
2. Never mix data between merchants/tenants.
3. Deterministic commerce facts beat LLM guesses.
4. Search before generation when a factual catalog answer is required.
5. Preserve conversation context, but allow explicit user corrections to override it.
6. Do not hardcode a particular product, category, brand, or language pattern as the only solution.
7. Every new planner capability gets multilingual regression tests.
8. Every external URL is validated before rendering or navigation.
9. Every expensive AI call should have measurable cost and latency.
10. A "no result" response should be useful: explain the gap and offer valid alternatives when possible.

## Definition of "World-Class"

The platform is ready for serious SaaS commercialization when a new merchant can:

1. create a store;
2. generate an API key;
3. connect a catalog;
4. confirm automatic field mapping;
5. sync products;
6. install the widget;
7. customize language/brand/currency;
8. handle multi-turn product conversations;
9. answer store-policy questions;
10. perform supported commerce actions;
11. see usage, cost, conversations, product demand, and conversion analytics;
12. operate safely under rate limits and tenant isolation.

The priority is not to add the largest number of AI features. The priority is to make the core commerce loop **correct, fast, universal, measurable, and safe**.
