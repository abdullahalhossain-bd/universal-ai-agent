# Merchant Console (dashboard)

React + Vite + Tailwind v4 dashboard for merchants: sign up / log in,
connect a website, manage API keys, and manage billing (Stripe).

This is separate from `frontend/` (the embeddable customer-facing
chat widget) — this app is for the *store owner*, not their
customers.

## Setup

```bash
npm install
cp .env.example .env   # optional — defaults to the dev proxy below
npm run dev
```

By default `npm run dev` proxies `/v1/*` requests to
`http://localhost:8000` (see `vite.config.js`) — start the FastAPI
backend on that port and this app talks to it with no extra config.
To point at a different backend, set `VITE_API_PROXY_TARGET` (dev) or
`VITE_API_BASE_URL` (prod build) in `.env`.

## Build

```bash
npm run build   # outputs to dist/
npm run preview # serve the production build locally
```

## What's wired up

- **Auth** (`/login`, `/signup`) — calls `POST /v1/auth/login` /
  `/v1/auth/signup`, stores the returned JWT in `localStorage`, and
  attaches it as `Authorization: Bearer <token>` on every subsequent
  request (see `src/api/client.js`).
- **Overview** (`/`) — usage-vs-budget, connected-website count,
  active-key count, pulled from `/v1/billing/summary`,
  `/v1/knowledge/websites`, `/v1/stores/me/api-keys`.
- **Websites** (`/websites`) — `POST /v1/knowledge/ingest` to crawl a
  site into the assistant's knowledge base, `GET
  /v1/knowledge/websites` to list what's connected.
- **API Keys** (`/api-keys`) — `GET/POST /v1/stores/me/api-keys`,
  `POST /v1/stores/me/api-keys/{id}/revoke`. The raw key is shown
  exactly once, at creation.
- **Billing** (`/billing`) — `GET /v1/billing/plans` +
  `/v1/billing/summary`, `POST /v1/billing/checkout-session` (Stripe
  Checkout redirect) and `/v1/billing/portal-session` (Stripe Billing
  Portal redirect). Requires `STRIPE_SECRET_KEY` /
  `STRIPE_PRICE_GROWTH` / `STRIPE_PRICE_PRO` set on the backend — see
  the repo root `.env.example`.

## Testing the Stripe flow locally

1. `stripe listen --forward-to localhost:8000/v1/billing/webhook`
   (prints a `whsec_...` — put it in the backend's
   `STRIPE_WEBHOOK_SECRET`).
2. Create a Growth/Pro product with a recurring price in the Stripe
   Dashboard (test mode), put the `price_...` IDs in
   `STRIPE_PRICE_GROWTH` / `STRIPE_PRICE_PRO`.
3. Click "Upgrade" on `/billing` — you'll land on Stripe's hosted
   Checkout (use card `4242 4242 4242 4242`, any future expiry/CVC).
4. On success you're redirected back to `/billing?checkout=success`;
   the actual plan/budget change happens when the webhook fires
   (usually within a second or two — refresh if it hasn't landed
   yet).
