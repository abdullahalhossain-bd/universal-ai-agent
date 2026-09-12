from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response


# No "/v1" prefix on purpose — merchants embed this at a short,
# stable, memorable URL:
#
#   <script src="https://YOUR_API_HOST/widget.js"
#           data-key="pk_live_xxxxxxxx" async></script>
#
router = APIRouter(tags=["Widget"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_WIDGET_PATH = _STATIC_DIR / "widget.js"
_ENHANCED_WIDGET_PATH = _STATIC_DIR / "widget-enhanced.js"
_PREMIUM_CSS_PATH = _STATIC_DIR / "premium-overrides.css"
_ADMIN_PATH = _STATIC_DIR / "admin.html"
_BRANDING_PATH = _STATIC_DIR / "branding.html"
_PLATFORM_ADMIN_PATH = _STATIC_DIR / "platform-admin.html"
_MERCHANT_CHAT_PATH = _STATIC_DIR / "merchant-chat.js"
_INBOX_PATH = _STATIC_DIR / "inbox.html"


@router.get("/widget.js")
async def widget_bundle() -> Response:
    """Return a lightweight, non-blocking merchant-branded widget loader.

    Important: the loader intentionally loads widget-core.js directly.
    widget-enhanced.js previously monkey-patched the host page's global
    window.fetch and installed a MutationObserver over the widget DOM. That
    made the merchant site share execution with enhancement logic and could
    cause freezes/jank. The core widget already uses Shadow DOM, so it is the
    safe production embed path.
    """
    loader = r'''/* Universal Commerce AI — lightweight merchant-branded widget loader. */
(function () {
  "use strict";

  var script = document.currentScript || document.scripts[document.scripts.length - 1];
  var key = script && script.getAttribute("data-key");
  if (!key) return;
  var apiBase = (script.getAttribute("data-api-base") || new URL(script.src, location.href).origin).replace(/\/$/, "");
  var loaded = false;

  function safeUrl(value) {
    if (typeof value !== "string") return "";
    var v = value.trim();
    return /^https?:\/\//i.test(v) ? v : "";
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function findWidgetRoot() {
    var nodes = document.body ? document.body.children : [];
    for (var i = 0; i < nodes.length; i++) {
      var root = nodes[i].shadowRoot;
      if (root && root.querySelector(".header") && root.querySelector(".panel")) return root;
    }
    return null;
  }

  function applyBranding(root, cfg) {
    if (!root) return;
    var header = root.querySelector(".header");
    var panel = root.querySelector(".panel");
    if (!header || !panel) return;

    var name = cfg.store_name || "Your Store";
    var assistant = cfg.assistant_name || "Shopping Assistant";
    var logo = safeUrl(cfg.logo_url);

    header.innerHTML = '<div class="brand-wrap" style="display:flex;align-items:center;gap:10px;min-width:0">' +
      (logo ? '<img src="' + esc(logo) + '" alt="" style="width:34px;height:34px;border-radius:9px;object-fit:cover;background:#fff;flex:0 0 auto" referrerpolicy="no-referrer">' : '') +
      '<div style="min-width:0"><strong style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(name) + '</strong>' +
      '<small>' + esc(assistant) + '</small></div></div>' +
      '<button class="close" type="button" aria-label="চ্যাট বন্ধ করুন">×</button>';
    panel.setAttribute("aria-label", name + " — " + assistant);

    var close = header.querySelector(".close");
    if (close) close.addEventListener("click", function () {
      var bubble = root.querySelector(".bubble");
      panel.classList.remove("open");
      if (bubble) { bubble.setAttribute("aria-expanded", "false"); bubble.focus(); }
    });
  }

  function loadCore(cfg) {
    if (loaded) return;
    loaded = true;

    var core = document.createElement("script");
    core.src = apiBase + "/widget-core.js";
    core.async = true;
    core.setAttribute("data-key", key);
    core.setAttribute("data-api-base", apiBase);
    core.setAttribute("data-color", cfg.brand_color || "#111827");
    core.setAttribute("data-greeting", cfg.greeting || "আসসালামু আলাইকুম! কীভাবে সাহায্য করতে পারি?");
    core.setAttribute("data-position", cfg.position === "bottom-left" ? "bottom-left" : "bottom-right");
    core.setAttribute("data-store-name", cfg.store_name || "Your Store");
    core.setAttribute("data-assistant-name", cfg.assistant_name || "Shopping Assistant");
    if (cfg.logo_url) core.setAttribute("data-logo", cfg.logo_url);

    core.onload = function () {
      var tries = 0;
      (function waitForRoot() {
        var root = findWidgetRoot();
        if (root) {
          applyBranding(root, cfg);
          return;
        }
        if (++tries < 20) setTimeout(waitForRoot, 50);
      })();
    };

    core.onerror = function () {
      loaded = false;
    };

    document.head.appendChild(core);
  }

  /* Configuration is optional and never blocks the merchant page. */
  fetch(apiBase + "/v1/stores/me/widget-config", {
    headers: { "x-api-key": key }
  })
    .then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    })
    .then(loadCore)
    .catch(function () {
      loadCore({
        store_name: "Your Store",
        assistant_name: "Shopping Assistant",
        brand_color: "#111827",
        greeting: "আসসালামু আলাইকুম! কীভাবে সাহায্য করতে পারি?",
        position: "bottom-right"
      });
    });
})();
'''
    return Response(
        content=loader,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@router.get("/widget-core.js")
async def widget_core_bundle() -> FileResponse:
    return FileResponse(
        _WIDGET_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@router.get("/widget-enhanced.js")
async def widget_enhanced_bundle() -> FileResponse:
    return FileResponse(
        _ENHANCED_WIDGET_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@router.get("/premium-overrides.css")
async def premium_overrides_css() -> FileResponse:
    """Premium visual layer, injected into the widget's shadow root."""
    return FileResponse(
        _PREMIUM_CSS_PATH,
        media_type="text/css",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@router.get("/merchant-chat.js")
async def merchant_chat_bundle() -> FileResponse:
    # NOTE: no longer loaded by the `/widget.js` bootstrap loader above.
    # `widget-core.js` (served from `app/static/widget.js`) contains its own
    # native live-support mode. Loading both creates duplicate polling loops.
    return FileResponse(
        _MERCHANT_CHAT_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@router.get("/admin")
async def admin_dashboard() -> FileResponse:
    return FileResponse(
        _ADMIN_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/admin/inbox")
async def merchant_inbox_dashboard() -> FileResponse:
    return FileResponse(
        _INBOX_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/admin/branding")
async def admin_branding_dashboard() -> FileResponse:
    return FileResponse(
        _BRANDING_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/platform-admin")
async def platform_admin_dashboard() -> FileResponse:
    return FileResponse(
        _PLATFORM_ADMIN_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )
