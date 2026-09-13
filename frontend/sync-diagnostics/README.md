# Sync diagnostics tool

A single-page, API-key-authenticated tool for inspecting one
datasource's sync health: data-quality score, field coverage, price/
stock change history, duplicate detection, and the schema-approval
workflow (approve/reject a changed field mapping before the next
sync).

**This is not the merchant dashboard.** The main product dashboard —
signup, login, billing, websites, API keys, chat preview, usage,
settings, platform admin — lives in `frontend-dashboard/` (a React
app, deployed separately; see `render.yaml`). This tool covers sync/
data-quality diagnostics that `frontend-dashboard/` doesn't have a
page for yet.

Served at `/sync-diagnostics?key=<api_key>&datasource=<id>` (mounted
in `app/main.py`). Auth is a raw `x-api-key` header, matching
`app/static/admin.html`'s onboarding tool — there's no JWT session
here, unlike `frontend-dashboard/`.

If you're adding a merchant-facing feature, it almost certainly
belongs in `frontend-dashboard/`, not here.
