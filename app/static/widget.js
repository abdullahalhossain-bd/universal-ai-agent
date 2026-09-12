/* Universal Commerce AI — isolated embeddable customer chat widget. */
(function () {
  "use strict";

  var script = document.currentScript || document.scripts[document.scripts.length - 1];
  var API_KEY = script && script.getAttribute("data-key");
  if (!API_KEY) return;

  var API_BASE = ((script.getAttribute("data-api-base") || new URL(script.src, location.href).origin)).replace(/\/$/, "");
  var ACCENT = script.getAttribute("data-color") || "#6366f1";
  var STORE_NAME = script.getAttribute("data-store-name") || "Store";
  var ASSISTANT_NAME = script.getAttribute("data-assistant-name") || "Shop AI";
  var LOGO = script.getAttribute("data-logo") || "";
  var GREETING = script.getAttribute("data-greeting") || "আমি আপনার AI শপিং সহকারী। পণ্য, দাম, স্টক বা অফার সম্পর্কে জিজ্ঞেস করুন।";
  var position = script.getAttribute("data-position") === "bottom-left" ? "left" : "right";

  var PREFIX = "ucai_widget_" + API_KEY.slice(-8);
  var CONV_KEY = PREFIX + "_conv";
  var TOKEN_KEY = PREFIX + "_conv_token";
  var VISITOR_KEY = PREFIX + "_visitor";
  var INTERACTION_KEY = PREFIX + "_interaction";
  var conversationId = null;
  var conversationToken = null;
  var visitorId = null;
  var merchantMode = false;
  var modeChanging = false;
  var sending = false;
  var greeted = false;
  var unread = 0;
  var pollTimer = null;
  var modeTimer = null;
  var lastMerchantIds = Object.create(null);
  var lastMerchantMessageId = 0;
  var interaction = null;
  var selectedImageId = null;

  function id() {
    try { if (crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (_) {}
    return "v_" + Date.now().toString(36) + Math.random().toString(36).slice(2);
  }
  function get(k) { try { return localStorage.getItem(k) || ""; } catch (_) { return ""; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
  function safeUrl(v) { return typeof v === "string" && /^https?:\/\//i.test(v.trim()) ? v.trim() : ""; }

  conversationId = get(CONV_KEY) || null;
  conversationToken = get(TOKEN_KEY) || null;
  visitorId = get(VISITOR_KEY);
  if (!visitorId) { visitorId = id(); set(VISITOR_KEY, visitorId); }
  try { interaction = JSON.parse(get(INTERACTION_KEY) || "null"); } catch (_) { interaction = null; }

  function persist(data) {
    if (!data) return;
    if (data.conversation_id) conversationId = String(data.conversation_id);
    if (data.conversation_token) conversationToken = String(data.conversation_token);
    if (conversationId) set(CONV_KEY, conversationId);
    if (conversationToken) set(TOKEN_KEY, conversationToken);
  }
  function resetConversation() {
    stopPolling();
    stopModeSync();
    conversationId = null;
    conversationToken = null;
    merchantMode = false;
    modeChanging = false;
    lastMerchantIds = Object.create(null);
    lastMerchantMessageId = 0;
    try { localStorage.removeItem(CONV_KEY); localStorage.removeItem(TOKEN_KEY); } catch (_) {}
    renderMode();
  }
  function headers(extra) {
    var h = extra || {};
    h["x-api-key"] = API_KEY;
    if (conversationToken) h["x-conversation-token"] = conversationToken;
    return h;
  }
  function request(url, options) {
    options = options || {};
    options.headers = headers(options.headers || {});
    return fetch(API_BASE + url, options).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) {
          var e = new Error((data && data.detail) || ("HTTP " + r.status));
          e.status = r.status;
          throw e;
        }
        return data;
      });
    });
  }
  function money(v, currency) {
    if (v === null || v === undefined || v === "") return "দাম জানতে যোগাযোগ করুন";
    var n = Number(v), c = String(currency || "").trim();
    if (Number.isFinite(n)) return (c ? c + " " : "") + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return (c ? c + " " : "") + String(v);
  }

  var host = document.createElement("div");
  host.style.cssText = "all:initial;position:fixed;z-index:2147483647;bottom:18px;" + position + ":18px;contain:layout style;";
  function mount() { if (!host.isConnected && document.body) document.body.appendChild(host); }
  mount();
  if (!host.isConnected) window.addEventListener("DOMContentLoaded", mount, { once: true });
  var shadow = host.attachShadow({ mode: "open" });
  var css = document.createElement("style");
  css.textContent =
    "*{box-sizing:border-box;font-family:Inter,'Segoe UI','Hind Siliguri',system-ui,sans-serif}" +
    ".shell{position:relative;color:#e2e8f0}" +
    ".bubble{position:relative;width:58px;height:58px;border:0;border-radius:20px;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;box-shadow:0 10px 26px rgba(79,70,229,.32);cursor:pointer;display:grid;place-items:center;transition:transform .18s ease,box-shadow .18s ease}.bubble:hover{transform:translateY(-2px);box-shadow:0 14px 30px rgba(79,70,229,.4)}.bubble svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:1.8}.badge{position:absolute;right:-4px;top:-4px;min-width:19px;height:19px;border-radius:999px;background:#ef4444;color:#fff;font:800 10px Inter;display:none;place-items:center;border:2px solid #090d16}.badge.show{display:grid}" +
    ".panel{position:absolute;bottom:72px;" + position + ":0;width:410px;max-width:calc(100vw - 24px);height:680px;max-height:calc(100vh - 36px);overflow:hidden;display:none;flex-direction:column;border:1px solid rgba(255,255,255,.1);border-radius:26px;background:#090d16;box-shadow:0 25px 80px rgba(0,0,0,.48),0 0 50px rgba(79,70,229,.13)}.panel.open{display:flex}" +
    ".glow{position:absolute;pointer-events:none;border-radius:999px;filter:blur(80px);opacity:.15}.g1{width:220px;height:220px;left:-80px;top:-70px;background:#4f46e5}.g2{width:230px;height:230px;right:-100px;top:35%;background:#7c3aed}.g3{display:none}" +
    ".header{position:relative;z-index:3;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.1);background:rgba(14,19,32,.94);display:flex;align-items:center;justify-content:space-between;gap:10px}.brand{display:flex;align-items:center;gap:10px;min-width:0}.avatar{position:relative;width:42px;height:42px;flex:none;border-radius:15px;padding:1.5px;background:linear-gradient(135deg,#4f46e5,#7c3aed);overflow:hidden}.avatar-inner{width:100%;height:100%;border-radius:13px;background:#0d1322;display:grid;place-items:center;overflow:hidden}.avatar-inner img{width:100%;height:100%;object-fit:cover}.avatar-inner svg{width:20px;height:20px;stroke:#a5b4fc;fill:none;stroke-width:1.7}.online{position:absolute;right:-1px;bottom:-1px;width:12px;height:12px;border-radius:50%;background:#10b981;border:2px solid #090d16}.brand-copy{min-width:0}.brand-name{font-size:14px;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tag{display:inline-flex;margin-left:5px;padding:2px 7px;border-radius:999px;background:rgba(99,102,241,.2);border:1px solid rgba(165,180,252,.3);color:#a5b4fc;font-size:9px;font-weight:700;vertical-align:2px}.status{display:flex;align-items:center;gap:5px;margin-top:3px;color:#34d399;font-size:10px;font-weight:600}.dot{width:6px;height:6px;border-radius:50%;background:#34d399}.close{border:0;background:transparent;color:#94a3b8;font-size:23px;line-height:1;padding:7px;border-radius:10px;cursor:pointer;flex:none}.close:hover{background:rgba(255,255,255,.08);color:#fff}" +
    ".modebar{position:relative;z-index:3;padding:8px 12px;border-bottom:1px solid rgba(255,255,255,.1);background:rgba(13,19,34,.96)}.mode-switch{padding:4px;border-radius:16px;background:rgba(9,13,22,.92);border:1px solid rgba(255,255,255,.1);display:flex;gap:3px}.mode-btn{flex:1;border:0;background:transparent;color:#94a3b8;border-radius:12px;padding:8px 5px;font-size:10.5px;font-weight:650;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:5px;min-height:36px}.mode-btn small{font-size:8px;opacity:.75}.mode-btn.active{background:linear-gradient(90deg,rgba(99,102,241,.28),rgba(168,85,247,.22));border:1px solid rgba(165,180,252,.38);color:#fff}.mode-btn.live.active{background:rgba(16,185,129,.13);border-color:rgba(52,211,153,.3)}.mode-note{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 2px 0;color:#94a3b8;font-size:9.5px}.live-note{color:#34d399;display:none}" +
    ".messages{position:relative;z-index:2;flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;padding:13px 14px 10px;display:flex;flex-direction:column;gap:10px;overscroll-behavior:contain;scroll-behavior:smooth}.messages::-webkit-scrollbar{width:3px}.messages::-webkit-scrollbar-thumb{background:rgba(148,163,184,.2);border-radius:99px}.today{align-self:center;padding:5px 10px;border-radius:999px;background:rgba(14,19,32,.72);border:1px solid rgba(255,255,255,.1);color:#94a3b8;font-size:9.5px}.msg{max-width:91%;padding:10px 12px;border-radius:15px;font-size:12px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.assistant{align-self:flex-start;background:linear-gradient(135deg,rgba(26,34,53,.78),rgba(15,23,42,.9));border:1px solid rgba(255,255,255,.1);color:#e2e8f0;border-top-left-radius:5px}.user{align-self:flex-end;background:linear-gradient(135deg,#4f46e5,#6366f1);color:#fff;border-bottom-right-radius:5px}.merchant{align-self:flex-start;background:rgba(16,185,129,.1);border:1px solid rgba(52,211,153,.25);color:#d1fae5;border-top-left-radius:5px}.typing{align-self:flex-start;background:rgba(255,255,255,.05);color:#94a3b8;padding:9px 12px}.typing-dots{display:flex;gap:4px}.typing-dots i{width:6px;height:6px;border-radius:50%;background:#94a3b8;animation:b 1s infinite}@keyframes b{0%,60%,100%{transform:translateY(0);opacity:.45}30%{transform:translateY(-4px);opacity:1}}" +
    ".welcome{align-self:flex-start;width:100%;display:flex;gap:8px}.mini-avatar{width:28px;height:28px;min-width:28px;margin-top:2px;border-radius:10px;background:rgba(99,102,241,.18);border:1px solid rgba(165,180,252,.28);display:grid;place-items:center}.mini-avatar svg{width:14px;height:14px;stroke:#a5b4fc;fill:none;stroke-width:2}.welcome-body{flex:1;min-width:0}.welcome-card{padding:12px 13px;border-radius:16px;border-top-left-radius:5px;background:linear-gradient(135deg,rgba(26,34,53,.76),rgba(15,23,42,.88));border:1px solid rgba(255,255,255,.1)}.welcome-bn{font-size:12px;line-height:1.65;color:#f1f5f9;font-weight:550}.welcome-en{font-size:10.5px;color:#cbd5e1;line-height:1.55;margin-top:8px}.divider{height:1px;background:rgba(255,255,255,.1);margin:9px 0}.example{color:#a5b4fc;font-weight:700}.discover{margin-top:8px;display:grid;gap:7px}.discover-card{width:100%;text-align:left;font:inherit;color:inherit;padding:9px 10px;border-radius:15px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.035);display:flex;align-items:center;justify-content:space-between;gap:8px;cursor:pointer;transition:background .15s ease}.discover-card:hover{background:rgba(255,255,255,.065)}.discover-main{display:flex;align-items:center;gap:8px;min-width:0}.discover-icon{width:28px;height:28px;border-radius:10px;display:grid;place-items:center;background:rgba(249,115,22,.12);font-size:13px;flex:none}.discover-title{font-size:10.5px;font-weight:750;color:#fff;overflow-wrap:anywhere}.discover-sub{font-size:9.5px;color:#94a3b8;margin-top:1px}.discover-arrow{color:#64748b;flex:none}" +
    ".products{align-self:flex-start;width:100%;display:grid;gap:8px}.product{overflow:hidden;border-radius:16px;background:linear-gradient(135deg,rgba(26,34,53,.72),rgba(15,23,42,.9));border:1px solid rgba(255,255,255,.1)}.product-img{width:100%;height:125px;object-fit:cover;background:#111827;display:block}.product-fallback{height:85px;display:grid;place-items:center;color:#64748b;font-size:10px;background:#111827}.product-body{padding:9px 10px}.product-name{font-size:11.5px;font-weight:750;color:#fff;line-height:1.35;overflow-wrap:anywhere}.product-meta{display:flex;justify-content:space-between;align-items:center;gap:6px;margin-top:6px}.price{font-size:13px;font-weight:800;color:#fff}.stock{font-size:9px;padding:3px 6px;border-radius:999px;background:rgba(16,185,129,.14);color:#6ee7b7}.stock.out{background:rgba(239,68,68,.12);color:#fca5a5}.stock.unknown{background:rgba(148,163,184,.1);color:#94a3b8}.rating{font-size:9px;color:#94a3b8;margin-top:4px}.actions{display:flex;gap:6px;margin-top:8px}.action{flex:1;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#cbd5e1;border-radius:9px;padding:7px;font-size:9.5px;font-weight:650;text-align:center;text-decoration:none;cursor:pointer}.action.primary{background:linear-gradient(90deg,#4f46e5,#6366f1);border-color:rgba(129,140,248,.5);color:#fff}" +
    ".quickbar{position:relative;z-index:3;padding:8px 12px;border-top:1px solid rgba(255,255,255,.1);background:rgba(14,19,32,.94);overflow-x:auto;display:flex;gap:6px}.quickbar::-webkit-scrollbar{display:none}.quick{flex:0 0 auto;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.045);color:#cbd5e1;border-radius:11px;padding:7px 9px;font-size:9.5px;font-weight:650;cursor:pointer;white-space:nowrap}" +
    ".composer-wrap{position:relative;z-index:3;padding:9px 11px 6px;border-top:1px solid rgba(255,255,255,.1);background:rgba(9,13,22,.96)}.composer{display:flex;align-items:flex-end;gap:6px}.input-shell{flex:1;display:flex;align-items:flex-end;background:rgba(17,23,38,.86);border:1px solid rgba(255,255,255,.14);border-radius:15px;min-width:0}.input-shell:focus-within{border-color:rgba(129,140,248,.85);box-shadow:0 0 0 3px rgba(99,102,241,.12)}.attach{border:0;background:transparent;color:#94a3b8;padding:9px 6px 9px 9px;cursor:pointer}.input{width:100%;min-height:38px;max-height:82px;resize:none;border:0;outline:0;background:transparent;color:#f1f5f9;padding:9px 4px;font-size:11.5px;line-height:1.4}.input::placeholder{color:#64748b}.send{height:38px;border:0;border-radius:13px;padding:0 13px;background:linear-gradient(90deg,#4f46e5,#7c3aed);color:#fff;font-size:10.5px;font-weight:750;cursor:pointer}.send:disabled{opacity:.55;cursor:wait}.footer{padding:5px 0 2px;text-align:center;color:#64748b;font-size:8.5px}.footer b{color:#818cf8}.security{margin-left:5px}.security span{color:#34d399}.preview{display:none;align-items:center;justify-content:space-between;padding:5px 8px;margin-bottom:5px;border-radius:9px;background:rgba(255,255,255,.04);color:#94a3b8;font-size:9px}.preview.show{display:flex}.remove{border:0;background:transparent;color:#94a3b8;cursor:pointer}" +
    "@media(max-width:520px){.panel{position:fixed;inset:0;width:100%;max-width:none;height:100%;max-height:none;border-radius:0}.bubble{width:54px;height:54px}.mode-btn{min-height:40px}.messages{padding:12px}.composer-wrap{padding:9px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}";
  shadow.appendChild(css);

  var wrap = document.createElement("div");
  wrap.className = "shell";
  wrap.innerHTML = '<button class="bubble" type="button" aria-label="চ্যাট খুলুন" aria-expanded="false"><svg viewBox="0 0 24 24"><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5 8.4 8.4 0 0 1-3.6-.8L4 20l1.2-4A7.3 7.3 0 0 1 5 11.5 7.5 7.5 0 0 1 12.5 4 7.5 7.5 0 0 1 20 11.5Z"/><path d="M9 12h.01M12.5 12h.01M16 12h.01"/></svg><span class="badge"></span></button>' +
    '<div class="panel" role="dialog" aria-modal="false" aria-label="AI Shopping Assistant"><div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>' +
    '<header class="header"><div class="brand"><div class="avatar"><div class="avatar-inner">' + (safeUrl(LOGO) ? '<img src="' + safeUrl(LOGO) + '" alt="">' : '<svg viewBox="0 0 24 24"><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/></svg>') + '</div><span class="online"></span></div><div class="brand-copy"><div class="brand-name"><span class="store-name"></span><span class="tag"></span></div><div class="status"><span class="dot"></span><span>Active • Instant answers</span></div></div></div><button class="close" type="button" aria-label="চ্যাট বন্ধ করুন">×</button></header>' +
    '<div class="modebar"><div class="mode-switch"><button class="mode-btn ai active" type="button"><span>AI Assistant</span></button><button class="mode-btn live" type="button"><span>লাইভ সাপোর্ট</span></button></div><div class="mode-note"><span class="mode-label">● Mode: AI Shopper</span><span class="live-note">Merchant support mode</span></div></div>' +
    '<div class="messages" role="log" aria-live="polite"></div>' +
    '<div class="quickbar"><button class="quick image-quick" type="button">📷 ছবি পাঠান</button><button class="quick">দাম ও স্টক জানতে চাই</button><button class="quick">সেরা অফার দেখান</button></div>' +
    '<div class="composer-wrap"><div class="preview"><span class="preview-name"></span><button class="remove" type="button">সরিয়ে দিন</button></div><input class="image-input" type="file" accept="image/jpeg,image/png,image/webp" hidden><form class="composer"><div class="input-shell"><button class="attach" type="button" aria-label="ছবি আপলোড করুন">⌑</button><textarea class="input" rows="1" maxlength="2000" aria-label="আপনার বার্তা" placeholder="পণ্য, দাম বা product link সম্পর্কে জিজ্ঞেস করুন…"></textarea></div><button class="send" type="submit">পাঠান</button></form><div class="footer">Powered by <b>Universal Commerce AI</b><span class="security">• <span>🔒</span> SSL Secured</span></div></div></div>';
  shadow.appendChild(wrap);

  var bubble = wrap.querySelector(".bubble"), panel = wrap.querySelector(".panel"), close = wrap.querySelector(".close");
  var messages = wrap.querySelector(".messages"), input = wrap.querySelector(".input"), send = wrap.querySelector(".send");
  var imageInput = wrap.querySelector(".image-input"), attach = wrap.querySelector(".attach"), preview = wrap.querySelector(".preview"), previewName = wrap.querySelector(".preview-name");
  var aiBtn = wrap.querySelector(".mode-btn.ai"), liveBtn = wrap.querySelector(".mode-btn.live");
  var liveNote = wrap.querySelector(".live-note"), modeLabel = wrap.querySelector(".mode-label"), remove = wrap.querySelector(".remove");
  wrap.querySelector(".store-name").textContent = STORE_NAME;
  wrap.querySelector(".tag").textContent = ASSISTANT_NAME;

  function scroll() { messages.scrollTop = messages.scrollHeight; }
  function add(role, text) {
    var el = document.createElement("div");
    el.className = "msg " + role;
    if (role === "typing") el.innerHTML = '<span class="typing-dots"><i></i><i></i><i></i></span>';
    else el.textContent = text || "";
    messages.appendChild(el); scroll();
    if (role !== "user" && role !== "typing" && !panel.classList.contains("open")) { unread++; updateBadge(); }
    return el;
  }
  function updateBadge() { var b = wrap.querySelector(".badge"); b.textContent = unread > 9 ? "9+" : String(unread); b.classList.toggle("show", unread > 0); }
  function showWelcome() {
    if (messages.querySelector(".welcome")) return;
    var el = document.createElement("div"); el.className = "welcome";
    el.innerHTML = '<div class="mini-avatar"><svg viewBox="0 0 24 24"><path d="M12 2l3.1 6.3L22 9.3l-5 4.9 1.2 6.8-6.2-3.2L12 18l-6.2 3.2L7 14.2 2 9.3l6.9-1L12 2Z"/></svg></div><div class="welcome-body"><div class="welcome-card"><div class="welcome-bn"></div><div class="divider"></div><div class="welcome-en">Hello! I\'m your AI shopping companion. Ask about prices, specs, stock, or product links.</div></div><div class="discover"><button class="discover-card" type="button"><div class="discover-main"><div class="discover-icon">🔥</div><div><div class="discover-title">Trending products</div><div class="discover-sub">See popular picks and current offers</div></div></div><span class="discover-arrow">›</span></button></div></div>';
    messages.appendChild(el);
    el.querySelector(".welcome-bn").textContent = GREETING;
    el.querySelector(".discover-card").addEventListener("click", function () { input.value = "ট্রেন্ডিং প্রোডাক্ট দেখান"; sendMessage(); });
    scroll();
  }
  function setOpen(open) {
    panel.classList.toggle("open", open);
    bubble.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { unread = 0; updateBadge(); input.focus(); startPolling(); syncMode(); }
    else stopPolling();
  }
  function renderMode() {
    aiBtn.classList.toggle("active", !merchantMode); liveBtn.classList.toggle("active", merchantMode);
    modeLabel.textContent = merchantMode ? "● Mode: Live merchant" : "● Mode: AI Shopper";
    liveNote.style.display = merchantMode ? "inline" : "none";
    input.placeholder = merchantMode ? "Write a message to the merchant…" : "পণ্য, দাম বা product link সম্পর্কে জিজ্ঞেস করুন…";
  }
  function setMode(active) {
    active = !!active;
    if (modeChanging || active === merchantMode) return;
    if (!conversationId || !conversationToken) {
      add("merchant", "প্রথমে AI-কে একটি message পাঠান। তারপর সরাসরি merchant-এর সাথে কথা বলতে পারবেন।");
      input.focus();
      return;
    }
    var previous = merchantMode;
    modeChanging = true;
    merchantMode = active;
    renderMode();
    request("/v1/messages/customer/" + encodeURIComponent(conversationId) + "/mode", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ mode: active ? "human" : "ai" })
    }).then(function (data) {
      merchantMode = !!(data && data.mode === "human");
      renderMode();
      if (merchantMode) { startPolling(); add("merchant", "লাইভ সাপোর্ট চালু হয়েছে। Merchant আপনার message দেখবেন।"); }
    }).catch(function (e) {
      merchantMode = previous;
      renderMode();
      if (e.status === 401 || e.status === 403 || e.status === 409) {
        resetConversation();
        add("assistant", "এই conversationটি আর access করা যাচ্ছে না। নতুন করে chat শুরু করুন।");
      } else add("merchant", "চ্যাট mode পরিবর্তন করা যায়নি। আবার চেষ্টা করুন।");
    }).finally(function () { modeChanging = false; });
  }
  function messagesUrl() {
    var base = "/v1/messages/customer/" + encodeURIComponent(conversationId);
    return lastMerchantMessageId ? base + "?after_id=" + encodeURIComponent(lastMerchantMessageId) : base;
  }
  function renderMerchantMessages(list) {
    if (!Array.isArray(list)) return;
    list.forEach(function (m) {
      if (!m || m.role !== "merchant" || m.id == null) return;
      var key = String(m.id);
      if (lastMerchantIds[key]) return;
      lastMerchantIds[key] = true;
      var n = Number(m.id);
      if (Number.isFinite(n) && n > lastMerchantMessageId) lastMerchantMessageId = n;
      add("merchant", "Store team: " + (m.content || ""));
    });
  }
  function syncMode() {
    if (!conversationId || !conversationToken || modeChanging) return;
    request(messagesUrl()).then(function (data) {
      if (!data) return;
      if (data.mode === "human" || data.mode === "ai") merchantMode = data.mode === "human";
      renderMode();
      if (merchantMode) renderMerchantMessages(data.messages);
    }).catch(function (e) {
      if (e.status === 401 || e.status === 403 || e.status === 409) {
        stopPolling(); stopModeSync(); resetConversation();
        if (panel.classList.contains("open")) add("assistant", "এই conversationটি আর access করা যাচ্ছে না। নতুন chat শুরু করুন।");
      }
    });
  }
  function startPolling() {
    if (pollTimer || !conversationId || !conversationToken) return;
    pollTimer = setInterval(function () {
      if (!conversationId || !conversationToken || modeChanging) return;
      request(messagesUrl()).then(function (data) {
        if (!data) return;
        if (data.mode === "human" && !merchantMode) { merchantMode = true; renderMode(); }
        else if (data.mode === "ai" && merchantMode && data.mode_owner !== "merchant") { merchantMode = false; renderMode(); }
        if (merchantMode) renderMerchantMessages(data.messages);
      }).catch(function (e) {
        if (e.status === 401 || e.status === 403 || e.status === 409) {
          stopPolling(); stopModeSync(); resetConversation();
          if (panel.classList.contains("open")) add("assistant", "এই conversationটি আর access করা যাচ্ছে না। নতুন chat শুরু করুন।");
        }
      });
    }, 5000);
  }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
  function startModeSync() { if (!modeTimer && conversationId && conversationToken) modeTimer = setInterval(syncMode, 5000); }
  function stopModeSync() { if (modeTimer) { clearInterval(modeTimer); modeTimer = null; } }

  function rememberInteraction(data) {
    if (!data || !data.interaction_id) return;
    interaction = { interaction_id: data.interaction_id, conversation_id: data.conversation_id || conversationId, product_ids: (data.products || []).map(function (p) { return p && p.id; }).filter(Boolean), ts: Date.now() };
    set(INTERACTION_KEY, JSON.stringify(interaction));
  }
  function track(type, productId, value) {
    if (!interaction || !interaction.interaction_id) return;
    fetch(API_BASE + "/v1/behavior/events", { method: "POST", headers: { "content-type": "application/json", "x-api-key": API_KEY }, body: JSON.stringify({ interaction_id: interaction.interaction_id, event_type: type, product_id: productId || null, conversation_id: conversationId, value: typeof value === "number" ? value : null, metadata: {} }), keepalive: true }).catch(function () {});
  }
  function addProducts(list, data) {
    if (!Array.isArray(list) || !list.length) return;
    rememberInteraction(data || {});
    var box = document.createElement("div"); box.className = "products";
    list.slice(0, 8).forEach(function (p) {
      var card = document.createElement("article"); card.className = "product";
      var image = safeUrl(p.image_url || p.image || p.main_image || p.thumbnail);
      if (image) { var img = document.createElement("img"); img.className = "product-img"; img.src = image; img.alt = p.name || "Product"; img.loading = "lazy"; img.onerror = function () { var f = document.createElement("div"); f.className = "product-fallback"; f.textContent = "ছবি পাওয়া যাচ্ছে না"; img.replaceWith(f); }; card.appendChild(img); }
      else { var f = document.createElement("div"); f.className = "product-fallback"; f.textContent = "ছবি পাওয়া যাচ্ছে না"; card.appendChild(f); }
      var body = document.createElement("div"); body.className = "product-body";
      var name = document.createElement("div"); name.className = "product-name"; name.textContent = p.name || p.title || "Product"; body.appendChild(name);
      var meta = document.createElement("div"); meta.className = "product-meta";
      var price = document.createElement("span"); price.className = "price"; price.textContent = money(p.price, p.currency_symbol || p.currency_code || p.currency); meta.appendChild(price);
      var stock = document.createElement("span"), sn = Number(p.stock), known = p.stock !== null && p.stock !== undefined && Number.isFinite(sn); stock.className = "stock" + (known && sn <= 0 ? " out" : known ? "" : " unknown"); stock.textContent = !known ? "স্টক জানা নেই" : sn > 0 ? "স্টকে আছে" : "স্টক শেষ"; meta.appendChild(stock); body.appendChild(meta);
      if (p.rating !== null && p.rating !== undefined) { var r = document.createElement("div"); r.className = "rating"; r.textContent = "★ " + Number(p.rating).toFixed(1) + (p.review_count ? " · " + Number(p.review_count).toLocaleString() + "টি review" : ""); body.appendChild(r); }
      var actions = document.createElement("div"); actions.className = "actions";
      var url = safeUrl(p.product_url || p.url || p.link), link = document.createElement("a"); link.className = "action primary"; link.textContent = url ? "Product দেখুন" : "Link নেই";
      if (url) { link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.addEventListener("click", function () { track("click", p.id); }); } else link.style.opacity = ".5";
      actions.appendChild(link);
      var ask = document.createElement("button"); ask.className = "action"; ask.type = "button"; ask.textContent = "Details"; ask.addEventListener("click", function () { input.value = (p.name || p.title || "Product") + " সম্পর্কে details চাই"; input.focus(); sendMessage(); }); actions.appendChild(ask);
      body.appendChild(actions); card.appendChild(body); box.appendChild(card);
    });
    messages.appendChild(box); scroll();
  }
  function setSending(v) { sending = v; send.disabled = v; input.disabled = v; attach.disabled = v; }
  function friendly(status) {
    if (status === 401 || status === 403) return "এই conversationটি আর access করা যাচ্ছে না। নতুন chat শুরু করুন।";
    if (status === 409) return "Conversation identity মেলেনি। নতুন chat শুরু করে আবার চেষ্টা করুন।";
    if (status === 413) return "ছবিটি একটু বড় হয়েছে। ছোট image পাঠান।";
    if (status === 429) return "একটু বেশি request হয়েছে 😊 কিছুক্ষণ পর আবার চেষ্টা করুন।";
    if (status >= 500) return "Service-এ সাময়িক সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।";
    return "এখন উত্তর দিতে সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।";
  }
  function sendMessage() {
    var text = input.value.trim();
    if (!text || sending) return;
    if (merchantMode) return sendMerchant(text);
    add("user", text); input.value = ""; input.style.height = "auto"; setSending(true);
    var typing = add("typing", "একটু দেখছি…");
    request("/v1/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: text, conversation_id: conversationId, visitor_id: visitorId }) })
      .then(function (data) { typing.remove(); persist(data); add("assistant", data.message || ""); addProducts(data.products, data); startPolling(); startModeSync(); })
      .catch(function (e) { typing.remove(); if (e.status === 401 || e.status === 403 || e.status === 409) resetConversation(); add("assistant", friendly(e.status)); })
      .finally(function () { setSending(false); input.focus(); });
  }
  function sendMerchant(text) {
    if (!conversationId || !conversationToken || sending || !merchantMode) return;
    setSending(true);
    request("/v1/messages/customer/" + encodeURIComponent(conversationId), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: text, visitor_id: visitorId }) })
      .then(function () { add("user", text); input.value = ""; input.style.height = "auto"; })
      .catch(function (e) { if (e.status === 401 || e.status === 403 || e.status === 409) { resetConversation(); add("assistant", friendly(e.status)); } else add("merchant", "Message পাঠানো যায়নি। আবার চেষ্টা করুন।"); })
      .finally(function () { setSending(false); input.focus(); });
  }
  function upload(file) {
    if (!file || sending) return;
    setSending(true); preview.classList.add("show"); previewName.textContent = "ছবি আপলোড হচ্ছে…";
    var form = new FormData(); form.append("file", file); if (conversationId) form.append("conversation_id", conversationId);
    fetch(API_BASE + "/v1/images", { method: "POST", headers: headers(), body: form }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) { var e = new Error((d && d.detail) || String(r.status)); e.status = r.status; throw e; } return d; }); })
      .then(function (data) { selectedImageId = data.image_id; previewName.textContent = "ছবি প্রস্তুত: " + (file.name || "image"); add("user", "📷 " + (file.name || "ছবি") + " পাঠিয়েছি।"); return request("/v1/images/" + encodeURIComponent(selectedImageId) + "/analyze", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ conversation_id: conversationId, question: input.value.trim() || null }) }); })
      .then(function (data) { persist(data); add("assistant", data.message || "ছবিটি দেখেছি।"); addProducts(data.products, data); clearImage(); startPolling(); startModeSync(); })
      .catch(function (e) { previewName.textContent = "ছবি পাঠানো যায়নি"; if (e.status === 401 || e.status === 403 || e.status === 409) resetConversation(); add("assistant", friendly(e.status)); })
      .finally(function () { setSending(false); input.focus(); });
  }
  function clearImage() { selectedImageId = null; imageInput.value = ""; preview.classList.remove("show"); previewName.textContent = ""; }

  bubble.addEventListener("click", function () { var open = !panel.classList.contains("open"); setOpen(open); if (open && !greeted) { greeted = true; var today = document.createElement("div"); today.className = "today"; today.textContent = "Today • AI Commerce Assistant"; messages.appendChild(today); showWelcome(); } });
  close.addEventListener("click", function () { setOpen(false); bubble.focus(); });
  aiBtn.addEventListener("click", function () { setMode(false); });
  liveBtn.addEventListener("click", function () { setMode(true); });
  attach.addEventListener("click", function () { imageInput.click(); });
  wrap.querySelector(".image-quick").addEventListener("click", function () { imageInput.click(); });
  imageInput.addEventListener("change", function () { if (imageInput.files && imageInput.files[0]) upload(imageInput.files[0]); });
  remove.addEventListener("click", clearImage);
  wrap.querySelector(".composer").addEventListener("submit", function (e) { e.preventDefault(); sendMessage(); });
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
  input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 82) + "px"; });
  wrap.querySelectorAll(".quick:not(.image-quick)").forEach(function (btn) { btn.addEventListener("click", function () { input.value = btn.textContent.trim(); input.focus(); }); });
  window.addEventListener("beforeunload", function () { stopPolling(); stopModeSync(); });

  renderMode();
  if (conversationId && conversationToken) { startPolling(); startModeSync(); }
  window.UniversalCommerceAI = window.UniversalCommerceAI || {};
  window.UniversalCommerceAI.trackConversion = function (type, opts) { opts = opts || {}; track(type, opts.product_id, opts.value); return true; };
  window.UniversalCommerceAI.trackAddToCart = function (productId, value) { track("add_to_cart", productId, value); return true; };
  window.UniversalCommerceAI.trackPurchase = function (value, productId) { track("purchase", productId, value); return true; };
})();
