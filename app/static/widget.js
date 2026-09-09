/* Universal Commerce AI — embeddable customer chat widget. */
(function () {
  "use strict";
  function safeUrl(url) { if (typeof url !== "string") return ""; var value = url.trim(); return /^https?:\/\//i.test(value) ? value : ""; }
  var script = document.currentScript || document.scripts[document.scripts.length - 1];
  var API_KEY = script && script.getAttribute("data-key"); if (!API_KEY) return;
  var API_BASE = ((script.getAttribute("data-api-base") || new URL(script.src, location.href).origin)).replace(/\/$/, "");
  var ACCENT = script.getAttribute("data-color") || "#111827";
  var GREETING = script.getAttribute("data-greeting") || "আসসালামু আলাইকুম! কীভাবে সাহায্য করতে পারি? পণ্য, দাম, স্টক বা product link সম্পর্কে জিজ্ঞেস করুন।";
  var position = script.getAttribute("data-position") === "bottom-left" ? "left" : "right";
  var STORAGE_KEY = "ucai_widget_conv_" + API_KEY.slice(-8), conversationId = null;
  try { conversationId = localStorage.getItem(STORAGE_KEY); } catch (_) {}
  var host = document.createElement("div"); host.style.cssText = "all:initial;position:fixed;z-index:2147483647;bottom:20px;" + position + ":20px;"; document.body.appendChild(host);
  var shadow = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent = "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}" +
    ".bubble{width:58px;height:58px;border:0;border-radius:50%;background:" + ACCENT + ";color:#fff;box-shadow:0 8px 28px rgba(0,0,0,.22);cursor:pointer;display:grid;place-items:center}.bubble svg{width:27px;height:27px;fill:#fff}" +
    ".panel{position:absolute;bottom:72px;" + position + ":0;width:390px;max-width:calc(100vw - 28px);height:610px;max-height:calc(100vh - 105px);background:#fff;border:1px solid #e5e7eb;border-radius:18px;box-shadow:0 18px 55px rgba(0,0,0,.22);display:none;overflow:hidden;flex-direction:column}.panel.open{display:flex}" +
    ".header{background:" + ACCENT + ";color:#fff;padding:15px 17px;display:flex;align-items:center;justify-content:space-between}.header strong{font-size:14px}.header small{display:block;opacity:.75;font-weight:400;margin-top:2px}.close{background:transparent;border:0;color:#fff;font-size:22px;cursor:pointer}" +
    ".messages{flex:1;overflow:auto;padding:15px;background:#f8fafc;display:flex;flex-direction:column;gap:10px}.msg{max-width:86%;padding:10px 13px;border-radius:14px;font-size:13.5px;line-height:1.5;white-space:pre-wrap}.user{align-self:flex-end;background:" + ACCENT + ";color:#fff;border-bottom-right-radius:4px}.assistant{align-self:flex-start;background:#fff;color:#172033;border:1px solid #e5e7eb;border-bottom-left-radius:4px}.typing{color:#9ca3af;font-style:italic}" +
    ".products{align-self:flex-start;width:min(100%,350px);display:grid;gap:10px}.product{background:#fff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;box-shadow:0 2px 8px rgba(15,23,42,.04)}.product-image{width:100%;height:155px;object-fit:cover;background:#f1f5f9;display:block}.product-body{padding:11px 12px}.product-name{font-weight:700;font-size:14px;color:#111827;line-height:1.35}.product-meta{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-top:7px}.price{font-size:15px;font-weight:800;color:#111827}.stock{font-size:11px;padding:3px 7px;border-radius:999px;background:#ecfdf5;color:#047857}.stock.out{background:#fef2f2;color:#b91c1c}.rating{font-size:11px;color:#64748b;margin-top:5px}.actions{display:flex;gap:7px;margin-top:10px}.action{flex:1;text-align:center;text-decoration:none;border:1px solid #dbe0e6;border-radius:9px;padding:7px 8px;font-size:11.5px;font-weight:600;color:#334155;background:#fff}.action.primary{background:" + ACCENT + ";border-color:" + ACCENT + ";color:#fff}.action.disabled{opacity:.5;pointer-events:none}" +
    ".composer{display:flex;gap:7px;padding:10px;border-top:1px solid #e5e7eb;background:#fff}.composer textarea{flex:1;min-height:40px;max-height:90px;resize:none;border:1px solid #d8dde5;border-radius:11px;padding:9px 10px;outline:0;font-size:13.5px}.composer textarea:focus{border-color:" + ACCENT + "}.composer button{border:0;background:" + ACCENT + ";color:#fff;border-radius:10px;padding:0 14px;font-weight:700;cursor:pointer}.composer button:disabled{opacity:.5}.footer{font-size:10px;text-align:center;color:#9ca3af;padding:4px 0 8px}";
  shadow.appendChild(style);
  var wrap = document.createElement("div");
  wrap.innerHTML = '<button class="bubble" aria-label="Open chat" type="button"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.03 2 11c0 2.28 1 4.35 2.66 5.94L4 22l5.29-1.4A11.1 11.1 0 0 0 12 21c5.52 0 10-4.03 10-9S17.52 2 12 2z"/></svg></button><div class="panel"><div class="header"><div><strong>AI Shopping Assistant</strong><small>Product, price, stock &amp; links</small></div><button class="close" type="button" aria-label="Close">×</button></div><div class="messages"></div><div class="composer"><textarea rows="1" maxlength="2000" placeholder="পণ্য, দাম বা link সম্পর্কে জিজ্ঞেস করুন…"></textarea><button class="send" type="button">Send</button></div><div class="footer">Powered by Universal Commerce AI</div></div>';
  shadow.appendChild(wrap);
  var bubble = wrap.querySelector(".bubble"), panel = wrap.querySelector(".panel"), close = wrap.querySelector(".close"), messages = wrap.querySelector(".messages"), input = wrap.querySelector("textarea"), send = wrap.querySelector(".send"), sending = false, greeted = false;
  function scroll() { messages.scrollTop = messages.scrollHeight; }
  function addMessage(role, text) { var el = document.createElement("div"); el.className = "msg " + role; el.textContent = text || ""; messages.appendChild(el); scroll(); return el; }
  function money(value) { if (value === null || value === undefined || value === "") return "Price on request"; var n = Number(value); return Number.isFinite(n) ? "৳" + n.toLocaleString("en-BD", { maximumFractionDigits: 0 }) : "৳" + String(value); }
  function addProducts(products) {
    if (!Array.isArray(products) || !products.length) return;
    var box = document.createElement("div"); box.className = "products";
    products.slice(0, 10).forEach(function (p) {
      var card = document.createElement("article"); card.className = "product";
      var image = safeUrl(p.image_url || p.image || p.main_image);
      if (image) { var img = document.createElement("img"); img.className = "product-image"; img.src = image; img.alt = p.name || "Product"; img.loading = "lazy"; card.appendChild(img); }
      var body = document.createElement("div"); body.className = "product-body";
      var name = document.createElement("div"); name.className = "product-name"; name.textContent = p.name || p.title || "Product"; body.appendChild(name);
      var meta = document.createElement("div"); meta.className = "product-meta";
      var price = document.createElement("span"); price.className = "price"; price.textContent = money(p.price); meta.appendChild(price);
      if (p.stock !== undefined && p.stock !== null) { var stock = document.createElement("span"); stock.className = "stock" + (Number(p.stock) <= 0 ? " out" : ""); stock.textContent = Number(p.stock) > 0 ? "In stock" : "Out of stock"; meta.appendChild(stock); }
      body.appendChild(meta);
      if (p.rating !== null && p.rating !== undefined) { var rating = document.createElement("div"); rating.className = "rating"; rating.textContent = "★ " + Number(p.rating).toFixed(1) + (p.review_count ? " · " + Number(p.review_count).toLocaleString() + " reviews" : ""); body.appendChild(rating); }
      var actions = document.createElement("div"); actions.className = "actions";
      var url = safeUrl(p.product_url || p.url || p.link); var link = document.createElement("a"); link.className = "action primary" + (url ? "" : " disabled"); link.textContent = url ? "View product" : "Link unavailable"; if (url) { link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; } actions.appendChild(link);
      var ask = document.createElement("button"); ask.className = "action"; ask.type = "button"; ask.textContent = "Ask about it"; ask.addEventListener("click", function () { input.value = (p.name || "this product") + " সম্পর্কে details চাই"; input.focus(); }); actions.appendChild(ask);
      body.appendChild(actions); card.appendChild(body); box.appendChild(card);
    });
    messages.appendChild(box); scroll();
  }
  function setSending(value) { sending = value; send.disabled = value; input.disabled = value; }
  function sendMessage() {
    var text = input.value.trim(); if (!text || sending) return; addMessage("user", text); input.value = ""; input.style.height = "auto"; setSending(true); var typing = addMessage("typing", "Thinking…");
    fetch(API_BASE + "/v1/chat", { method: "POST", headers: { "content-type": "application/json", "x-api-key": API_KEY }, body: JSON.stringify({ message: text, conversation_id: conversationId }) }).then(function (r) { if (!r.ok) throw new Error("HTTP_" + r.status); return r.json(); }).then(function (data) { typing.remove(); if (data.conversation_id) { conversationId = data.conversation_id; try { localStorage.setItem(STORAGE_KEY, conversationId); } catch (_) {} } addMessage("assistant", data.message || ""); addProducts(data.products); }).catch(function () { typing.remove(); addMessage("assistant", "দুঃখিত, এখন উত্তর দিতে সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।"); }).finally(function () { setSending(false); input.focus(); });
  }
  bubble.addEventListener("click", function () { panel.classList.toggle("open"); if (!greeted) { greeted = true; addMessage("assistant", GREETING); } if (panel.classList.contains("open")) input.focus(); });
  close.addEventListener("click", function () { panel.classList.remove("open"); }); send.addEventListener("click", sendMessage);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
  input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 90) + "px"; });
})();
