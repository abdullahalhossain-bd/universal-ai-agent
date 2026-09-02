from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


# No "/v1" prefix on purpose — merchants embed this at a short,
# stable, memorable URL:
#
#   <script src="https://YOUR_API_HOST/widget.js"
#           data-key="pk_live_xxxxxxxx" async></script>
#
router = APIRouter(tags=["Widget"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_WIDGET_PATH = _STATIC_DIR / "widget.js"
_ADMIN_PATH = _STATIC_DIR / "admin.html"
_PLATFORM_ADMIN_PATH = _STATIC_DIR / "platform-admin.html"


@router.get("/widget.js")
async def widget_bundle() -> FileResponse:

    return FileResponse(
        _WIDGET_PATH,
        media_type="application/javascript",
        headers={
            # Merchant sites load this on every page view, and it
            # has no per-store content baked in (config comes from
            # the <script> tag's own data-* attributes) — safe to
            # cache aggressively at the edge/browser. Bump this if
            # a CDN sits in front and you need faster rollout of
            # widget changes.
            "Cache-Control": "public, max-age=300",
        },
    )


@router.get("/admin")
async def admin_dashboard() -> FileResponse:

    # Single-file onboarding dashboard: create a store, connect
    # data (crawl or DB datasource), test the assistant, then get
    # the widget embed snippet. It calls the same-origin /v1/*
    # API directly from the browser using the merchant's own
    # pk_ key (entered or generated in-page) — no separate admin
    # auth system exists yet, so this piggybacks on the API key
    # exactly like the chat widget does. Not cached: unlike
    # widget.js this is the thing merchants iterate against, so
    # a stale cached copy after a dashboard update is more
    # confusing than a re-fetch on every visit is expensive.
    return FileResponse(
        _ADMIN_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/platform-admin")
async def platform_admin_dashboard() -> FileResponse:

    # The operator-only control panel — separate page, separate auth
    # (app/api/routes/admin.py's /v1/admin/login, a PlatformAdmin
    # session JWT) from the merchant onboarding page above. It has
    # no store's pk_ key baked in and isn't reachable with one; the
    # login form on this page is the only way in. Not cached, same
    # reasoning as /admin.
    return FileResponse(
        _PLATFORM_ADMIN_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )