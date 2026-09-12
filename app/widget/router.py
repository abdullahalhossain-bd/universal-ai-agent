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
  var UX_CSS = [
    "/* Embedded-widget UX layer: isolated inside Shadow DOM. */",
    ".shell{font-family:Inter,'Segoe UI','Hind Siliguri',system-ui,sans-serif!important;color:#172033!important}",
    ".panel{width:min(420px,calc(100vw - 24px))!important;height:min(700px,calc(100vh - 32px))!important;max-height:calc(100vh - 32px)!important;background:#ffffff!important;border:1px solid #e5e7eb!important;border-radius:22px!important;box-shadow:0 24px 70px rgba(15,23,42,.22),0 8px 24px rgba(15,23,42,.10)!important}",
    ".header{background:#ffffff!important;color:#111827!important;border-bottom:1px solid #eef2f7!important;backdrop-filter:none!important;padding:14px 16px!important}",
    ".header .brand-name,.header strong{color:#111827!important}",
    ".header .status{color:#047857!important}.header .close{color:#64748b!important}.header .close:hover{background:#f1f5f9!important;color:#0f172a!important}",
    ".modebar{background:#f8fafc!important;border-bottom:1px solid #eef2f7!important;backdrop-filter:none!important;padding:8px 12px!important}",
    ".mode-switch{background:#eef2f7!important;border:0!important}.mode-btn{color:#64748b!important}.mode-btn.active{background:#ffffff!important;color:#111827!important;border:1px solid #dbe2ea!important;box-shadow:0 2px 7px rgba(15,23,42,.08)!important}.mode-btn.live.active{background:#ecfdf5!important;color:#047857!important;border-color:#a7f3d0!important}",
    ".mode-note{color:#64748b!important}",
    ".messages{background:#f8fafc!important;padding:14px 14px 12px!important;gap:9px!important;overflow-x:hidden!important;overscroll-behavior:contain!important}",
    ".msg,.welcome-card,.product,.discover-card{max-width:92%!important;min-width:0!important;overflow-wrap:anywhere!important;word-break:break-word!important}",
    ".msg{font-size:13px!important;line-height:1.55!important;white-space:pre-wrap!important}",
    ".assistant{background:#ffffff!important;color:#1f2937!important;border:1px solid #e5e7eb!important;box-shadow:0 1px 3px rgba(15,23,42,.06)!important}",
    ".user{background:#334155!important;color:#ffffff!important;border:0!important;box-shadow:0 4px 12px rgba(15,23,42,.14)!important}",
    ".merchant{background:#ecfdf5!important;color:#14532d!important;border:1px solid #bbf7d0!important;box-shadow:0 1px 3px rgba(15,23,42,.05)!important}",
    ".typing{background:#ffffff!important;color:#64748b!important;border:1px solid #e5e7eb!important}",
    ".welcome-card{background:#ffffff!important;color:#1f2937!important;border:1px solid #e5e7eb!important;box-shadow:0 1px 3px rgba(15,23,42,.05)!important}",
    ".welcome-bn{color:#1f2937!important}.welcome-en{color:#64748b!important}.example{color:#4338ca!important}",
    ".discover-card{background:#ffffff!important;border:1px solid #e5e7eb!important}.discover-card.support{background:#ecfdf5!important;border-color:#bbf7d0!important}.discover-title{color:#111827!important}.discover-sub{color:#64748b!important}.support .discover-title{color:#14532d!important}.support-action{background:#047857!important;color:#fff!important;border:0!important}",
    ".products{min-width:0!important}.product{background:#ffffff!important;border:1px solid #e5e7eb!important;color:#1f2937!important;box-shadow:0 2px 8px rgba(15,23,42,.05)!important}.product-name{color:#111827!important}.price{color:#111827!important}",
    ".composer{background:#ffffff!important;border-top:1px solid #eef2f7!important;padding:10px 12px!important;gap:8px!important;min-width:0!important}",
    ".composer-input,.composer textarea{min-width:0!important;width:100%!important;background:#f8fafc!important;color:#111827!important;border:1px solid #dbe2ea!important;border-radius:14px!important;outline:none!important;box-shadow:none!important;overflow-wrap:anywhere!important;word-break:break-word!important}",
    ".composer-input:focus,.composer textarea:focus{border-color:#94a3b8!important;box-shadow:0 0 0 3px rgba(100,116,139,.12)!important}",
    ".composer-send{background:#334155!important;color:#fff!important;border:0!important}.composer-icon-btn,.tool{background:#f8fafc!important;color:#475569!important;border:1px solid #e2e8f0!important}",
    ".composer-input ~ .composer-input,.composer textarea ~ textarea{display:none!important}",
    ".panel .composer + .composer,.panel .composer ~ .composer{display:none!important}",
    ".shell:has(.panel.open) .bubble{opacity:0!important;visibility:hidden!important;pointer-events:none!important;transform:scale(.82)!important}",
    ".panel.open + .bubble{opacity:0!important;visibility:hidden!important;pointer-events:none!important}",
    ".messages,.messages *{max-width:100%}",
    ".messages img,.product-image{max-width:100%!important}",
    ".footer{color:#94a3b8!important;background:#fff!important}",
    "@media(max-width:520px){.panel{position:fixed!important;inset:8px!important;width:auto!important;height:auto!important;max-height:none!important;border-radius:18px!important}.bubble{width:54px!important;height:54px!important}.messages{padding-left:12px!important;padding-right:12px!important}}",
    "@media(prefers-reduced-motion:reduce){.panel,.bubble,.msg{animation:none!important;transition:none!important}}"
  ].join("");

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

  function installUx(root) {
    if (!root || root.querySelector("style[data-ucai-ux]")) return;
    var style = document.createElement("style");
    style.setAttribute("data-ucai-ux", "true");
    style.textContent = UX_CSS;
    root.appendChild(style);
  }

  function applyBranding(root, cfg) {
    if (!root) return;
    installUx(root);
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
