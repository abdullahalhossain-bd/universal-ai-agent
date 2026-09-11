/*!
 * Universal Commerce AI — standalone full-page chat page.
 *
 * Open as:  /chat/?key=pk_live_xxxxxxxx
 * or paste the key into the connect screen on first visit.
 */
(function () {
  "use strict";

  var API_BASE = window.location.origin;
  var STORAGE_PREFIX = "uai_chat_";

  function isSafeWebUrl(url) {
    if (typeof url !== "string") return false;
    var trimmed = url.trim();
    return /^https?:\/\//i.test(trimmed);
  }

  var gate = document.getElementById("gate");
  var gateForm = document.getElementById("gate-form");
  var gateInput = document.getElementById("gate-key");
  var gateError = document.getElementById("gate-error");
  var app = document.getElementById("app");
  var thread = document.getElementById("thread");
  var statusDot = document.getElementById("status-dot");
  var storeNameEl = document.getElementById("store-name");
  var resetBtn = document.getElementById("reset-btn");
  var composer = document.getElementById("composer");
  var messageInput = document.getElementById("message-input");
  var sendBtn = document.getElementById("send-btn");
  var attachBtn = document.getElementById("attach-btn");
  var fileInput = document.getElementById("file-input");
  var attachPreview = document.getElementById("attach-preview");

  var apiKey = null;
  var conversationId = null;
  var conversationToken = null;
  var visitorId = null;
  var pendingImage = null;
  var sending = false;

  function keyStorageName() { return STORAGE_PREFIX + "key"; }
  function convoStorageName(key) { return STORAGE_PREFIX + "convo_" + key; }
  function tokenStorageName(key) { return STORAGE_PREFIX + "token_" + key; }
  function visitorStorageName(key) { return STORAGE_PREFIX + "visitor_" + key; }

  function makeVisitorId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    } catch (_) {}
    var bytes = new Uint8Array(16);
    try { if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes); } catch (_) {}
    if (!bytes.some(function (b) { return b !== 0; })) for (var i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    return "v_" + Array.prototype.map.call(bytes, function (b) { return b.toString(16).padStart(2, "0"); }).join("");
  }

  function resolveKey() {
    var params = new URLSearchParams(window.location.search);
    var fromQuery = params.get("key");
    if (fromQuery) {
      try { localStorage.setItem(keyStorageName(), fromQuery); } catch (e) {}
      return fromQuery;
    }
    try { return localStorage.getItem(keyStorageName()); } catch (e) { return null; }
  }

  function loadConversationState(key) {
    try { conversationId = localStorage.getItem(convoStorageName(key)); } catch (e) { conversationId = null; }
    try { conversationToken = localStorage.getItem(tokenStorageName(key)); } catch (e) { conversationToken = null; }
    try {
      visitorId = localStorage.getItem(visitorStorageName(key));
      if (!visitorId) { visitorId = makeVisitorId(); localStorage.setItem(visitorStorageName(key), visitorId); }
    } catch (e) { visitorId = makeVisitorId(); }
  }

  function persistConversation(data) {
    if (!data) return;
    if (data.conversation_id) conversationId = String(data.conversation_id);
    if (data.conversation_token) conversationToken = String(data.conversation_token);
    try {
      if (conversationId) localStorage.setItem(convoStorageName(apiKey), conversationId);
      if (conversationToken) localStorage.setItem(tokenStorageName(apiKey), conversationToken);
    } catch (e) {}
  }

  function clearConversation() {
    conversationId = null;
    conversationToken = null;
    try {
      localStorage.removeItem(convoStorageName(apiKey));
      localStorage.removeItem(tokenStorageName(apiKey));
    } catch (e) {}
  }

  function apiHeaders(extra) {
    var headers = Object.assign({ "x-api-key": apiKey }, extra || {});
    if (conversationToken) headers["x-conversation-token"] = conversationToken;
    return headers;
  }

  function init() {
    var key = resolveKey();
    if (!key) { gate.hidden = false; gateInput.focus(); return; }
    startApp(key);
  }

  gateForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var value = gateInput.value.trim();
    if (!value) return;
    gateError.hidden = true;
    try { localStorage.setItem(keyStorageName(), value); } catch (e) {}
    startApp(value);
  });

  function startApp(key) {
    apiKey = key;
    loadConversationState(key);
    gate.hidden = true;
    app.hidden = false;
    renderEmptyState();
    probeConnection();
    messageInput.focus();
  }

  function probeConnection() {
    fetch(API_BASE + "/health").then(function (res) { setStatus(res.ok ? "online" : "error"); }).catch(function () { setStatus("error"); });
  }
  function setStatus(state) { statusDot.className = "dot dot-" + state; }
  function showGateError(msg) { gate.hidden = false; app.hidden = true; gateError.textContent = msg; gateError.hidden = false; }

  function renderEmptyState() {
    thread.innerHTML = '<div class="empty"><p class="empty-title">How can I help?</p><p>Ask about a product, sizing, availability, or shipping — I\'ll answer from the store\'s own catalog.</p></div>';
  }
  function clearEmptyState() { var empty = thread.querySelector(".empty"); if (empty) empty.remove(); }

  function escapeHtml(str) { var div = document.createElement("div"); div.textContent = str == null ? "" : String(str); return div.innerHTML; }
  var CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20ac", GBP: "\u00a3", JPY: "\u00a5", INR: "\u20b9", BDT: "\u09f3", AUD: "A$", CAD: "C$", CNY: "\u00a5" };
  function formatPrice(price, currency) { if (price === null || price === undefined) return null; var num = Number(price); if (Number.isNaN(num)) return null; var code = (currency || "USD").toUpperCase(); var symbol = CURRENCY_SYMBOLS[code]; return symbol ? symbol + num.toFixed(2) : num.toFixed(2) + " " + code; }
  function resolveMediaUrl(url) { if (!url) return url; if (/^https?:\/\//i.test(url)) return url; return API_BASE + url; }

  function appendMessage(role, opts) {
    opts = opts || {}; clearEmptyState();
    var wrap = document.createElement("div"); wrap.className = "msg msg-" + role + (opts.error ? " msg-error" : "");
    if (opts.imageUrl) { var img = document.createElement("img"); img.className = "msg-image"; img.src = resolveMediaUrl(opts.imageUrl); img.alt = "Uploaded photo"; wrap.appendChild(img); }
    if (opts.text) { var bubble = document.createElement("div"); bubble.className = "bubble"; bubble.textContent = opts.text; wrap.appendChild(bubble); }
    if (opts.products && opts.products.length) wrap.appendChild(renderProducts(opts.products, opts.interactionId, opts.query));
    if (opts.sources && opts.sources.length) wrap.appendChild(renderSources(opts.sources));
    thread.appendChild(wrap); thread.scrollTop = thread.scrollHeight; return wrap;
  }

  function renderProducts(products, interactionId, query) {
    var list = document.createElement("div"); list.className = "products";
    products.forEach(function (p) {
      var card = document.createElement("div"); card.className = "product-tag";
      var thumbHtml = p.image_url ? '<img class="product-thumb" src="' + escapeHtml(resolveMediaUrl(p.image_url)) + '" alt="" loading="lazy" />' : '<div class="product-thumb"></div>';
      var priceLabel = formatPrice(p.price, p.currency);
      card.innerHTML = thumbHtml + '<div class="product-info"><p class="product-name">' + escapeHtml(p.name || "Product") + "</p><p class="product-meta">" + (p.stock !== null && p.stock !== undefined ? (p.stock > 0 ? "In stock" : "Out of stock") : "") + "</p></div>" + (priceLabel ? '<span class="product-price">' + escapeHtml(priceLabel) + "</span>" : "");
      card.appendChild(renderProductActions(p, interactionId, query)); list.appendChild(card);
    });
    return list;
  }

  function renderProductActions(product, interactionId, query) {
    var actions = document.createElement("div"); actions.className = "product-actions";
    if (product.product_url && isSafeWebUrl(product.product_url)) {
      var viewLink = document.createElement("a"); viewLink.className = "product-action"; viewLink.href = product.product_url.trim(); viewLink.target = "_blank"; viewLink.rel = "noopener noreferrer"; viewLink.textContent = "View product";
      viewLink.addEventListener("click", function () { trackBehaviorEvent(product.id, "click", interactionId, query); }); actions.appendChild(viewLink);
    }
    var detailsBtn = document.createElement("button"); detailsBtn.type = "button"; detailsBtn.className = "product-action"; detailsBtn.textContent = "Details"; detailsBtn.addEventListener("click", function () { trackBehaviorEvent(product.id, "detail_view", interactionId, query); askAboutProduct(product, true); }); actions.appendChild(detailsBtn);
    var askBtn = document.createElement("button"); askBtn.type = "button"; askBtn.className = "product-action product-action-ghost"; askBtn.textContent = "Ask about it"; askBtn.addEventListener("click", function () { askAboutProduct(product, false); }); actions.appendChild(askBtn);
    return actions;
  }

  function askAboutProduct(product, sendImmediately) {
    var name = (product && product.name) || "this product"; var prompt = "Tell me more about " + name;
    if (sendImmediately) { if (sending) return; appendMessage("user", { text: prompt }); sendTextMessage(prompt); return; }
    messageInput.value = prompt + " "; messageInput.focus(); messageInput.style.height = "auto"; messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px"; sendBtn.disabled = sending || !messageInput.value.trim();
    try { messageInput.setSelectionRange(messageInput.value.length, messageInput.value.length); } catch (e) {}
  }

  function renderSources(sources) {
    var wrap = document.createElement("div"); wrap.className = "sources";
    sources.forEach(function (s) { var label = s.title || s.url || "Source"; var chip; if (s.url) { chip = document.createElement("a"); chip.href = isSafeWebUrl(s.url) ? s.url.trim() : "#"; chip.target = "_blank"; chip.rel = "noopener noreferrer"; } else chip = document.createElement("span"); chip.className = "source-chip"; chip.textContent = label; wrap.appendChild(chip); });
    return wrap;
  }

  function showTyping() { var wrap = document.createElement("div"); wrap.className = "msg msg-assistant typing"; wrap.id = "typing-indicator"; wrap.innerHTML = '<div class="bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>'; thread.appendChild(wrap); thread.scrollTop = thread.scrollHeight; }
  function hideTyping() { var el = document.getElementById("typing-indicator"); if (el) el.remove(); }

  function randomId() { if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID(); return "id-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2); }
  function trackBehaviorEvent(productId, eventType, interactionId, query) {
    if (!productId || !apiKey) return;
    fetch(API_BASE + "/v1/behavior/events", { method: "POST", headers: apiHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ interaction_id: interactionId || randomId(), event_type: eventType, product_id: productId, conversation_id: conversationId, query: query || null }) }).catch(function () {});
  }

  function persistConversationId(id) { if (!id) return; persistConversation({ conversation_id: id }); }

  function sendTextMessage(text) {
    setSending(true); showTyping();
    fetch(API_BASE + "/v1/chat", { method: "POST", headers: apiHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ message: text, conversation_id: conversationId, visitor_id: visitorId }) })
      .then(handleApiResponse)
      .then(function (data) { persistConversation(data); setStatus("online"); appendMessage("assistant", { text: data.message, products: data.products, sources: data.sources, interactionId: data.interaction_id || randomId(), query: text }); })
      .catch(function (err) { handleSendError(err); })
      .finally(function () { hideTyping(); setSending(false); });
  }

  function sendImageMessage(file, question) {
    setSending(true); showTyping();
    var form = new FormData(); form.append("file", file); if (conversationId) form.append("conversation_id", conversationId);
    fetch(API_BASE + "/v1/images", { method: "POST", headers: apiHeaders(), body: form })
      .then(handleApiResponse)
      .then(function (uploaded) { return fetch(API_BASE + "/v1/images/" + uploaded.image_id + "/analyze", { method: "POST", headers: apiHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ conversation_id: conversationId, question: question || null }) }).then(handleApiResponse); })
      .then(function (data) { persistConversation(data); setStatus("online"); appendMessage("assistant", { text: data.message, products: data.products, sources: data.sources, interactionId: data.interaction_id || randomId(), query: question || null }); })
      .catch(function (err) { handleSendError(err); })
      .finally(function () { hideTyping(); setSending(false); clearAttachment(); });
  }

  function handleApiResponse(res) {
    if (res.status === 401) { throw { userMessage: "This conversation is no longer available. Please start a new conversation.", invalidKey: false, resetConversation: true }; }
    if (res.status === 403) { throw { userMessage: "This conversation token is invalid. Please start a new conversation.", resetConversation: true }; }
    if (res.status === 409) { throw { userMessage: "This conversation belongs to a different visitor identity. Please start a new conversation.", resetConversation: true }; }
    if (res.status === 429) { throw { userMessage: "Too many messages right now — try again in a moment." }; }
    if (!res.ok) { throw { userMessage: "Something went wrong on the store's end. Please try again." }; }
    return res.json();
  }

  function handleSendError(err) {
    setStatus("error");
    if (err && err.resetConversation) clearConversation();
    if (err && err.invalidKey) { try { localStorage.removeItem(keyStorageName()); } catch (e) {} showGateError(err.userMessage); return; }
    appendMessage("assistant", { text: (err && err.userMessage) || "Couldn't reach the store right now. Check your connection and try again.", error: true });
  }

  function setSending(state) { sending = state; sendBtn.disabled = state || (!messageInput.value.trim() && !pendingImage); }

  messageInput.addEventListener("input", function () { messageInput.style.height = "auto"; messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px"; sendBtn.disabled = sending || (!messageInput.value.trim() && !pendingImage); });
  messageInput.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); composer.requestSubmit(); } });

  composer.addEventListener("submit", function (e) {
    e.preventDefault(); if (sending) return;
    var text = messageInput.value.trim();
    if (pendingImage) { appendMessage("user", { text: text || null, imageUrl: pendingImage.previewUrl }); sendImageMessage(pendingImage.file, text); }
    else { if (!text) return; appendMessage("user", { text: text }); sendTextMessage(text); }
    messageInput.value = ""; messageInput.style.height = "auto"; setSending(sending);
  });

  attachBtn.addEventListener("click", function () { fileInput.click(); });
  fileInput.addEventListener("change", function () {
    var file = fileInput.files && fileInput.files[0]; if (!file) return;
    pendingImage = { file: file, previewUrl: URL.createObjectURL(file) };
    attachPreview.hidden = false; attachPreview.innerHTML = escapeHtml(file.name) + ' <button type="button" id="attach-clear">Remove</button>';
    document.getElementById("attach-clear").addEventListener("click", clearAttachment); sendBtn.disabled = false; fileInput.value = "";
  });

  function clearAttachment() { if (pendingImage) URL.revokeObjectURL(pendingImage.previewUrl); pendingImage = null; attachPreview.hidden = true; attachPreview.innerHTML = ""; sendBtn.disabled = sending || !messageInput.value.trim(); }

  resetBtn.addEventListener("click", function () { clearConversation(); renderEmptyState(); clearAttachment(); });
  init();
})();
