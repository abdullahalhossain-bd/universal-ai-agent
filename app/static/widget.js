/* Universal Commerce AI — embeddable customer chat widget. */
(function () {
  "use strict";

  function safeUrl(url) {
    if (typeof url !== "string") return "";
    var value = url.trim();
    return /^https?:\/\//i.test(value) ? value : "";
  }

  var script = document.currentScript || document.scripts[document.scripts.length - 1];
  var API_KEY = script && script.getAttribute("data-key");
  if (!API_KEY) return;

  var API_BASE = ((script.getAttribute("data-api-base") || new URL(script.src, location.href).origin)).replace(/\/$/, "");
  var ACCENT = script.getAttribute("data-color") || "#111827";
  var GREETING = script.getAttribute("data-greeting") || "আসসালামু আলাইকুম! কীভাবে সাহায্য করতে পারি? পণ্য, দাম, স্টক বা product link সম্পর্কে জিজ্ঞেস করুন।";
  var position = script.getAttribute("data-position") === "bottom-left" ? "left" : "right";
  var STORAGE_PREFIX = "ucai_widget_" + API_KEY.slice(-8);
  var STORAGE_KEY = STORAGE_PREFIX + "_conv";
  var TOKEN_KEY = STORAGE_PREFIX + "_conv_token";
  var VISITOR_KEY = STORAGE_PREFIX + "_visitor";
  var INTERACTION_KEY = "ucai_widget_interaction_" + API_KEY.slice(-8);
  var INTERACTION_TTL_MS = 24 * 60 * 60 * 1000;
  var conversationId = null;
  var conversationToken = null;
  var visitorId = null;
  var pollingTimer = null;
  var lastMerchantMessageId = null;
  var lastInteraction = null;

  function makeVisitorId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    } catch (_) {}
    var bytes = new Uint8Array(16);
    try { if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes); } catch (_) {}
    if (!bytes.some(function (b) { return b !== 0; })) {
      for (var i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    }
    var hex = Array.prototype.map.call(bytes, function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    return "v_" + hex;
  }

  try { conversationId = localStorage.getItem(STORAGE_KEY); } catch (_) {}
  try { conversationToken = localStorage.getItem(TOKEN_KEY); } catch (_) {}
  try {
    visitorId = localStorage.getItem(VISITOR_KEY);
    if (!visitorId) { visitorId = makeVisitorId(); localStorage.setItem(VISITOR_KEY, visitorId); }
  } catch (_) { visitorId = makeVisitorId(); }
  try {
    var storedInteraction = JSON.parse(localStorage.getItem(INTERACTION_KEY) || "null");
    if (storedInteraction && Date.now() - Number(storedInteraction.ts || 0) < INTERACTION_TTL_MS) lastInteraction = storedInteraction;
  } catch (_) {}

  function persistConversation(data) {
    if (!data) return;
    if (data.conversation_id) conversationId = String(data.conversation_id);
    if (data.conversation_token) conversationToken = String(data.conversation_token);
    try {
      if (conversationId) localStorage.setItem(STORAGE_KEY, conversationId);
      if (conversationToken) localStorage.setItem(TOKEN_KEY, conversationToken);
    } catch (_) {}
  }

  function clearConversation() {
    conversationId = null;
    conversationToken = null;
    lastMerchantMessageId = null;
    try { localStorage.removeItem(STORAGE_KEY); localStorage.removeItem(TOKEN_KEY); } catch (_) {}
  }

  function conversationHeaders(extra) {
    var headers = extra || {};
    if (conversationToken) headers["x-conversation-token"] = conversationToken;
    return headers;
  }

  var host = document.createElement("div");
  host.style.cssText = "all:initial;position:fixed;z-index:2147483647;bottom:20px;" + position + ":20px;";
  document.body.appendChild(host);
  var shadow = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent = "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}" +
    ".bubble{width:58px;height:58px;border:0;border-radius:50%;background:" + ACCENT + ";color:#fff;box-shadow:0 8px 28px rgba(0,0,0,.22);cursor:pointer;display:grid;place-items:center}.bubble:focus-visible,.close:focus-visible,.composer button:focus-visible,.tool:focus-visible,.action:focus-visible,.product-option:focus-visible{outline:3px solid #93c5fd;outline-offset:2px}.bubble svg{width:27px;height:27px;fill:#fff}" +
    ".panel{position:absolute;bottom:72px;" + position + ":0;width:390px;max-width:calc(100vw - 28px);height:610px;max-height:calc(100vh - 105px);background:#fff;border:1px solid #e5e7eb;border-radius:18px;box-shadow:0 18px 55px rgba(0,0,0,.22);display:none;overflow:hidden;flex-direction:column}.panel.open{display:flex}" +
    ".header{background:" + ACCENT + ";color:#fff;padding:15px 17px;display:flex;align-items:center;justify-content:space-between}.header strong{font-size:14px}.header small{display:block;opacity:.75;font-weight:400;margin-top:2px}.close{background:transparent;border:0;color:#fff;font-size:22px;cursor:pointer}" +
    ".messages{flex:1;overflow:auto;padding:15px;background:#f8fafc;display:flex;flex-direction:column;gap:10px}.msg{max-width:86%;padding:10px 13px;border-radius:14px;font-size:13.5px;line-height:1.5;white-space:pre-wrap}.user{align-self:flex-end;background:" + ACCENT + ";color:#fff;border-bottom-right-radius:4px}.assistant{align-self:flex-start;background:#fff;color:#172033;border:1px solid #e5e7eb;border-bottom-left-radius:4px}.merchant{align-self:flex-start;background:#f0fdf4;color:#14532d;border:1px solid #bbf7d0;border-bottom-left-radius:4px}.typing{color:#9ca3af;font-style:italic}" +
    ".products{align-self:flex-start;width:min(100%,350px);display:grid;gap:10px}.product{background:#fff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;box-shadow:0 2px 8px rgba(15,23,42,.04);transition:.18s}.product:hover{transform:translateY(-1px);box-shadow:0 7px 20px rgba(15,23,42,.09)}.product-image{width:100%;height:155px;object-fit:cover;background:#f1f5f9;display:block}.product-image-fallback{height:155px;background:#f1f5f9;color:#64748b;display:grid;place-items:center;font-size:12px}.product-body{padding:11px 12px}.product-option{width:100%;border:0;background:transparent;padding:0;text-align:left;cursor:pointer}.product-option-row{display:flex;align-items:flex-start;gap:8px}.product-number{width:24px;height:24px;min-width:24px;border-radius:8px;background:#f1f5f9;color:#475569;display:grid;place-items:center;font-size:11px;font-weight:800}.product-name{font-weight:700;font-size:14px;color:#111827;line-height:1.35}.product-meta{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-top:7px}.price{font-size:15px;font-weight:800;color:#111827}.stock{font-size:11px;padding:3px 7px;border-radius:999px;background:#ecfdf5;color:#047857}.stock.out{background:#fef2f2;color:#b91c1c}.stock.unknown{background:#f8fafc;color:#64748b}.rating{font-size:11px;color:#64748b;margin-top:5px}.actions{display:flex;gap:7px;margin-top:10px}.action{flex:1;text-align:center;text-decoration:none;border:1px solid #dbe0e6;border-radius:9px;padding:7px 8px;font-size:11.5px;font-weight:600;color:#334155;background:#fff;cursor:pointer}.action.primary{background:" + ACCENT + ";border-color:" + ACCENT + ";color:#fff}.action.disabled{opacity:.5;pointer-events:none}.composer{display:flex;gap:7px;padding:10px;border-top:1px solid #e5e7eb;background:#fff;align-items:flex-end}.composer textarea{flex:1;min-height:40px;max-height:90px;resize:none;border:1px solid #d8dde5;border-radius:11px;padding:9px 10px;outline:0;font-size:13.5px}.composer textarea:focus{border-color:" + ACCENT + "}.composer button{border:0;background:" + ACCENT + ";color:#fff;border-radius:10px;padding:0 14px;height:40px;font-weight:700;cursor:pointer}.composer button:disabled{opacity:.5}.tools{display:flex;gap:6px;padding:7px 10px 0;background:#fff}.tool{border:1px solid #d8dde5;background:#fff;border-radius:8px;padding:5px 8px;font-size:11px;color:#475569;cursor:pointer}.preview{display:none;padding:6px 10px;background:#fff;border-top:1px solid #f1f5f9;font-size:11px;color:#475569}.preview.show{display:flex;justify-content:space-between;align-items:center}.footer{font-size:10px;text-align:center;color:#9ca3af;padding:4px 0 8px}";
  shadow.appendChild(style);

  var wrap = document.createElement("div");
  wrap.innerHTML = '<button class="bubble" aria-label="চ্যাট খুলুন" aria-expanded="false" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2C6.48 2 2 6.03 2 11c0 2.28 1 4.35 2.66 5.94L4 22l5.29-1.4A11.1 11.1 0 0 0 12 21c5.52 0 10-4.03 10-9S17.52 2 12 2z"/></svg></button><div class="panel" role="dialog" aria-label="AI Shopping Assistant" aria-modal="false"><div class="header"><div><strong>AI Shopping Assistant</strong><small>পণ্য, দাম, স্টক ও product link</small></div><button class="close" type="button" aria-label="চ্যাট বন্ধ করুন">×</button></div><div class="messages" role="log" aria-live="polite" aria-relevant="additions"></div><div class="preview"><span class="preview-name"></span><button class="tool preview-remove" type="button">সরিয়ে দিন</button></div><div class="tools"><input class="image-input" type="file" accept="image/jpeg,image/png,image/webp" hidden><button class="tool image-button" type="button" aria-label="ছবি আপলোড করুন">📷 ছবি পাঠান</button></div><div class="composer"><textarea rows="1" maxlength="2000" aria-label="আপনার বার্তা" placeholder="পণ্য, দাম বা product link সম্পর্কে জিজ্ঞেস করুন…"></textarea><button class="send" type="button">পাঠান</button></div><div class="footer">Powered by Universal Commerce AI</div></div>';
  shadow.appendChild(wrap);

  var bubble = wrap.querySelector(".bubble");
  var panel = wrap.querySelector(".panel");
  var close = wrap.querySelector(".close");
  var messages = wrap.querySelector(".messages");
  var input = wrap.querySelector("textarea");
  var send = wrap.querySelector(".send");
  var imageInput = wrap.querySelector(".image-input");
  var imageButton = wrap.querySelector(".image-button");
  var preview = wrap.querySelector(".preview");
  var previewName = wrap.querySelector(".preview-name");
  var previewRemove = wrap.querySelector(".preview-remove");
  var sending = false;
  var greeted = false;
  var selectedImageId = null;

  function scroll() { messages.scrollTop = messages.scrollHeight; }
  function addMessage(role, text) { var el = document.createElement("div"); el.className = "msg " + role; el.textContent = text || ""; messages.appendChild(el); scroll(); return el; }
  function money(value, currency) { if (value === null || value === undefined || value === "") return "দাম জানতে যোগাযোগ করুন"; var n = Number(value), cur = String(currency || "").trim(); if (Number.isFinite(n)) { var formatted = n.toLocaleString(undefined, { maximumFractionDigits: 2 }); return cur ? cur + " " + formatted : formatted; } return cur ? cur + " " + String(value) : String(value); }

  function rememberInteraction(interactionId, convId, productIds) {
    if (!interactionId) return;
    lastInteraction = { interaction_id: interactionId, conversation_id: convId || null, product_ids: productIds || [], ts: Date.now() };
    try { localStorage.setItem(INTERACTION_KEY, JSON.stringify(lastInteraction)); } catch (_) {}
  }

  function trackEvent(eventType, opts) {
    opts = opts || {};
    var interactionId = opts.interaction_id || (lastInteraction && lastInteraction.interaction_id);
    if (!interactionId) return false;
    var payload = { interaction_id: interactionId, event_type: eventType, product_id: opts.product_id || (lastInteraction && lastInteraction.product_ids && lastInteraction.product_ids[0]) || null, conversation_id: opts.conversation_id || (lastInteraction && lastInteraction.conversation_id) || conversationId || null, value: typeof opts.value === "number" ? opts.value : null, metadata: opts.metadata || {} };
    try { fetch(API_BASE + "/v1/behavior/events", { method: "POST", headers: { "content-type": "application/json", "x-api-key": API_KEY }, body: JSON.stringify(payload), keepalive: true }).catch(function () {}); } catch (_) {}
    return true;
  }

  function askAboutProduct(p) {
    var name = p.name || p.title || "এই product";
    input.value = name + " সম্পর্কে details চাই";
    input.focus();
    sendMessage();
  }

  function addProducts(products, interactionId, convId) {
    if (!Array.isArray(products) || !products.length) return;
    var productIds = products.map(function (p) { return p && p.id; }).filter(Boolean);
    rememberInteraction(interactionId, convId, productIds);
    var box = document.createElement("div"); box.className = "products";
    products.slice(0, 10).forEach(function (p, index) {
      var card = document.createElement("article"); card.className = "product";
      var image = safeUrl(p.image_url || p.image || p.main_image || p.thumbnail);
      if (image) {
        var img = document.createElement("img"); img.className = "product-image"; img.src = image; img.alt = p.name || "Product"; img.loading = "lazy";
        img.addEventListener("error", function () { var fallback = document.createElement("div"); fallback.className = "product-image-fallback"; fallback.textContent = "ছবি পাওয়া যাচ্ছে না"; img.replaceWith(fallback); }); card.appendChild(img);
      } else { var fallback = document.createElement("div"); fallback.className = "product-image-fallback"; fallback.textContent = "ছবি পাওয়া যাচ্ছে না"; card.appendChild(fallback); }
      var body = document.createElement("div"); body.className = "product-body";
      var option = document.createElement("button"); option.className = "product-option"; option.type = "button"; option.setAttribute("aria-label", "এই product সম্পর্কে জানতে চাই");
      var row = document.createElement("span"); row.className = "product-option-row";
      var number = document.createElement("span"); number.className = "product-number"; number.textContent = String(index + 1); row.appendChild(number);
      var name = document.createElement("span"); name.className = "product-name"; name.textContent = p.name || p.title || "Product"; row.appendChild(name);
      option.appendChild(row); option.addEventListener("click", function () { askAboutProduct(p); }); body.appendChild(option);
      var meta = document.createElement("div"); meta.className = "product-meta";
      var price = document.createElement("span"); price.className = "price"; price.textContent = money(p.price, p.currency_symbol || p.currency_code || p.currency); meta.appendChild(price);
      var stock = document.createElement("span"); var stockNumber = Number(p.stock); stock.className = "stock" + (p.stock !== null && p.stock !== undefined && Number.isFinite(stockNumber) && stockNumber <= 0 ? " out" : " unknown"); stock.textContent = p.stock === null || p.stock === undefined || !Number.isFinite(stockNumber) ? "স্টক জানা নেই" : (stockNumber > 0 ? "স্টকে আছে" : "স্টক শেষ"); meta.appendChild(stock); body.appendChild(meta);
      if (p.rating !== null && p.rating !== undefined) { var ratingValue = Number(p.rating); var rating = document.createElement("div"); rating.className = "rating"; rating.textContent = "★ " + (Number.isFinite(ratingValue) ? ratingValue.toFixed(1) : String(p.rating)) + (p.review_count ? " · " + Number(p.review_count).toLocaleString(undefined) + "টি review" : ""); body.appendChild(rating); }
      var actions = document.createElement("div"); actions.className = "actions";
      var url = safeUrl(p.product_url || p.url || p.link);
      var link = document.createElement("a"); link.className = "action primary" + (url ? "" : " disabled"); link.textContent = url ? "Product দেখুন" : "Link নেই";
      if (url) { link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.addEventListener("click", function () { trackEvent("click", { product_id: p.id, interaction_id: interactionId, conversation_id: convId }); }); }
      actions.appendChild(link);
      var ask = document.createElement("button"); ask.className = "action"; ask.type = "button"; ask.textContent = "Details"; ask.addEventListener("click", function () { askAboutProduct(p); });
      actions.appendChild(ask); body.appendChild(actions); card.appendChild(body); box.appendChild(card);
    });
    messages.appendChild(box); scroll();
  }

  function setSending(value) { sending = value; send.disabled = value; input.disabled = value; imageButton.disabled = value; }
  function clearImage() { selectedImageId = null; imageInput.value = ""; preview.classList.remove("show"); previewName.textContent = ""; }
  function friendlyError(status) { if (status === 401 || status === 403) return "দুঃখিত, এই conversationটি আর access করা যাচ্ছে না। নতুন conversation শুরু করছি—আবার পাঠান।"; if (status === 409) return "এই conversation-এর visitor identity মেলেনি। নতুন conversation শুরু করে আবার চেষ্টা করুন।"; if (status === 413) return "ছবিটি একটু বড় হয়েছে। ছোট একটি image পাঠান।"; if (status === 429) return "একটু বেশি request হয়ে গেছে 😊 কিছুক্ষণ পর আবার চেষ্টা করুন।"; if (status >= 500) return "দুঃখিত, আমাদের service-এ সাময়িক সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।"; return "দুঃখিত, এখন উত্তর দিতে সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।"; }

  function uploadImage(file) {
    if (!file || sending) return;
    setSending(true); preview.classList.add("show"); previewName.textContent = "ছবি আপলোড হচ্ছে…";
    var form = new FormData(); form.append("file", file); if (conversationId) form.append("conversation_id", conversationId);
    fetch(API_BASE + "/v1/images", { method: "POST", headers: { "x-api-key": API_KEY }, body: form })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (data) { selectedImageId = data.image_id; previewName.textContent = "ছবি প্রস্তুত: " + (file.name || "image"); addMessage("user", "📷 " + (file.name || "ছবি") + " পাঠিয়েছি."); return fetch(API_BASE + "/v1/images/" + encodeURIComponent(selectedImageId) + "/analyze", { method: "POST", headers: { "content-type": "application/json", "x-api-key": API_KEY }, body: JSON.stringify({ conversation_id: conversationId, question: input.value.trim() || null }) }); })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (data) { persistConversation(data); addMessage("assistant", data.message || "ছবিটি দেখেছি。"); addProducts(data.products, data.interaction_id, data.conversation_id); clearImage(); startPolling(); })
      .catch(function (err) { previewName.textContent = "ছবি পাঠানো যায়নি"; addMessage("assistant", friendlyError(Number(err.message))); })
      .finally(function () { setSending(false); input.focus(); });
  }

  function startPolling() {
    if (!conversationId || !conversationToken || pollingTimer) return;
    pollingTimer = setInterval(function () {
      fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversationId), { headers: conversationHeaders({ "x-api-key": API_KEY }) })
        .then(function (r) {
          if (r.status === 401 || r.status === 403) { stopPolling(); clearConversation(); return null; }
          if (!r.ok) return null;
          return r.json();
        })
        .then(function (data) { if (!data || !Array.isArray(data.messages)) return; data.messages.forEach(function (m) { if (m.role !== "merchant" || !m.id || m.id === lastMerchantMessageId) return; lastMerchantMessageId = m.id; addMessage("merchant", "Store team: " + (m.content || "")); }); })
        .catch(function () {});
    }, 5000);
  }
  function stopPolling() { if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; } }

  function sendMessage() {
    var text = input.value.trim(); if (!text || sending) return;
    addMessage("user", text); input.value = ""; input.style.height = "auto"; setSending(true);
    var typing = addMessage("typing", "একটু দেখছি…");
    var body = { message: text, conversation_id: conversationId, visitor_id: visitorId };
    var headers = conversationHeaders({ "content-type": "application/json", "x-api-key": API_KEY });
    fetch(API_BASE + "/v1/chat", { method: "POST", headers: headers, body: JSON.stringify(body) })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) { clearConversation(); throw new Error(String(r.status)); }
        if (r.status === 409) { clearConversation(); throw new Error("409"); }
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then(function (data) { typing.remove(); persistConversation(data); addMessage("assistant", data.message || ""); addProducts(data.products, data.interaction_id, data.conversation_id); startPolling(); })
      .catch(function (err) { typing.remove(); addMessage("assistant", friendlyError(Number(err.message)) || "দুঃখিত, এখন উত্তর দিতে সমস্যা হচ্ছে।"); })
      .finally(function () { setSending(false); input.focus(); });
  }

  function setOpen(open) { panel.classList.toggle("open", open); bubble.setAttribute("aria-expanded", open ? "true" : "false"); if (open) { input.focus(); startPolling(); } }
  bubble.addEventListener("click", function () { var open = !panel.classList.contains("open"); setOpen(open); if (open && !greeted) { greeted = true; addMessage("assistant", GREETING); } });
  close.addEventListener("click", function () { setOpen(false); bubble.focus(); });
  send.addEventListener("click", sendMessage);
  imageButton.addEventListener("click", function () { imageInput.click(); });
  imageInput.addEventListener("change", function () { if (imageInput.files && imageInput.files[0]) uploadImage(imageInput.files[0]); });
  previewRemove.addEventListener("click", clearImage);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
  input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 90) + "px"; });
  window.addEventListener("beforeunload", stopPolling);

  window.UniversalCommerceAI = window.UniversalCommerceAI || {};
  window.UniversalCommerceAI.trackConversion = function (eventType, opts) { return trackEvent(eventType, opts); };
  window.UniversalCommerceAI.trackAddToCart = function (productId, value) { return trackEvent("add_to_cart", { product_id: productId, value: value }); };
  window.UniversalCommerceAI.trackPurchase = function (value, productId) { return trackEvent("purchase", { product_id: productId, value: value }); };
})();
