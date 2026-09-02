/*!
 * Universal Commerce AI — embeddable chat widget.
 *
 * Merchant embed snippet:
 *   <script src="https://YOUR_API_HOST/widget.js"
 *           data-key="pk_live_xxxxxxxx"
 *           async></script>
 *
 * Optional attributes on the same <script> tag:
 *   data-api-base   override API origin (defaults to this script's own origin)
 *   data-color      accent color, any valid CSS color (default "#111827")
 *   data-greeting   first assistant bubble shown on open (default provided)
 *   data-position   "bottom-right" | "bottom-left" (default "bottom-right")
 *
 * Design notes:
 *   - Everything renders inside a Shadow DOM so the merchant's page
 *     CSS can never leak in and this widget's CSS can never leak out.
 *   - No build step, no dependencies. One file, IIFE, safe to load
 *     with `async` or `defer` on any page.
 *   - `data-key` is a public-facing key (meant to sit in page source
 *     on the open web) — it authenticates the chat endpoint only.
 *     Do NOT put a secret/admin key here.
 *   - conversation_id is kept in localStorage per store key so a
 *     returning visitor keeps their thread; if storage is unavailable
 *     (privacy mode, etc.) the widget falls back to an in-memory id
 *     and still works for the current page view.
 */
(function () {
  "use strict";

  // ---------------------------------
  // Config from the <script> tag
  // ---------------------------------

  var thisScript =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      return scripts[scripts.length - 1];
    })();

  var API_KEY = thisScript.getAttribute("data-key");

  if (!API_KEY) {
    console.error(
      "[widget] missing data-key attribute on the widget <script> tag — widget not started."
    );
    return;
  }

  var scriptOrigin = (function () {
    try {
      return new URL(thisScript.src, window.location.href).origin;
    } catch (e) {
      return window.location.origin;
    }
  })();

  var API_BASE = (
    thisScript.getAttribute("data-api-base") || scriptOrigin
  ).replace(/\/$/, "");

  var ACCENT = thisScript.getAttribute("data-color") || "#111827";
  var POSITION =
    thisScript.getAttribute("data-position") === "bottom-left"
      ? "bottom-left"
      : "bottom-right";
  var GREETING =
    thisScript.getAttribute("data-greeting") ||
    "Hi! Ask me anything about our products.";

  var STORAGE_KEY = "ucai_widget_conv_" + API_KEY.slice(-8);

  // ---------------------------------
  // Small storage helper (fails silently)
  // ---------------------------------

  var memoryFallback = {};
  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return memoryFallback[key] || null;
    }
  }
  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      memoryFallback[key] = value;
    }
  }

  // ---------------------------------
  // Host element + Shadow DOM
  // ---------------------------------

  var host = document.createElement("div");
  host.id = "ucai-chat-widget-host";
  // Keep the host itself out of page layout flow; everything
  // inside is positioned by the shadow tree's own CSS.
  host.style.all = "initial";
  host.style.position = "fixed";
  host.style.zIndex = "2147483647";
  host.style[POSITION === "bottom-left" ? "left" : "right"] = "20px";
  host.style.bottom = "20px";

  document.body.appendChild(host);

  var shadow = host.attachShadow({ mode: "open" });

  var style = document.createElement("style");
  style.textContent =
    ":host{all:initial;}" +
    "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}" +
    ".bubble{" +
    "width:56px;height:56px;border-radius:50%;background:" +
    ACCENT +
    ";box-shadow:0 4px 14px rgba(0,0,0,.25);border:none;cursor:pointer;" +
    "display:flex;align-items:center;justify-content:center;transition:transform .15s ease;}" +
    ".bubble:hover{transform:scale(1.05);}" +
    ".bubble svg{width:26px;height:26px;fill:#fff;}" +
    ".panel{" +
    "position:absolute;bottom:72px;" +
    (POSITION === "bottom-left" ? "left:0;" : "right:0;") +
    "width:360px;max-width:calc(100vw - 40px);height:520px;max-height:70vh;" +
    "background:#fff;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.22);" +
    "display:none;flex-direction:column;overflow:hidden;border:1px solid rgba(0,0,0,.06);}" +
    ".panel.open{display:flex;}" +
    ".header{background:" +
    ACCENT +
    ";color:#fff;padding:14px 16px;font-size:14px;font-weight:600;" +
    "display:flex;align-items:center;justify-content:space-between;}" +
    ".header button{background:transparent;border:none;color:#fff;cursor:pointer;font-size:18px;line-height:1;padding:4px;opacity:.85;}" +
    ".header button:hover{opacity:1;}" +
    ".messages{flex:1;overflow-y:auto;padding:14px;background:#f7f7f8;display:flex;flex-direction:column;gap:10px;}" +
    ".msg{max-width:82%;padding:9px 12px;border-radius:12px;font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word;}" +
    ".msg.user{align-self:flex-end;background:" +
    ACCENT +
    ";color:#fff;border-bottom-right-radius:3px;}" +
    ".msg.assistant{align-self:flex-start;background:#fff;color:#1f2328;border:1px solid #e6e6e9;border-bottom-left-radius:3px;}" +
    ".msg.error{align-self:flex-start;background:#fdecea;color:#7a1f1a;border:1px solid #f3c6c2;}" +
    ".msg.typing{align-self:flex-start;color:#9a9aa0;font-style:italic;}" +
    ".products{display:flex;flex-direction:column;gap:6px;margin-top:2px;max-width:82%;align-self:flex-start;}" +
    ".product{border:1px solid #e6e6e9;background:#fff;border-radius:10px;padding:8px 10px;font-size:12.5px;text-decoration:none;color:#1f2328;display:block;}" +
    ".product:hover{border-color:" +
    ACCENT +
    ";}" +
    ".product .name{font-weight:600;display:block;}" +
    ".product .price{color:#5a5a63;}" +
    ".composer{display:flex;gap:8px;padding:10px;border-top:1px solid #eceef0;background:#fff;}" +
    ".composer textarea{flex:1;resize:none;border:1px solid #dcdde0;border-radius:10px;padding:9px 10px;" +
    "font-size:13.5px;line-height:1.4;max-height:90px;min-height:38px;outline:none;}" +
    ".composer textarea:focus{border-color:" +
    ACCENT +
    ";}" +
    ".composer button{border:none;background:" +
    ACCENT +
    ";color:#fff;border-radius:10px;padding:0 14px;cursor:pointer;font-size:13px;font-weight:600;}" +
    ".composer button:disabled{opacity:.5;cursor:default;}" +
    ".footer-note{font-size:10.5px;color:#b1b1b8;text-align:center;padding:4px 0 8px;}";

  shadow.appendChild(style);

  var wrap = document.createElement("div");
  wrap.style.position = "relative";
  shadow.appendChild(wrap);

  wrap.innerHTML =
    '<button class="bubble" aria-label="Open chat" type="button">' +
    '<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.03 2 11c0 2.28 1 4.35 2.66 5.94L4 22l5.29-1.4A11.1 11.1 0 0 0 12 21c5.52 0 10-4.03 10-9s-4.48-10-10-10z"/></svg>' +
    "</button>" +
    '<div class="panel">' +
    '<div class="header"><span>Chat with us</span><button class="close" aria-label="Close chat" type="button">&times;</button></div>' +
    '<div class="messages"></div>' +
    '<div class="composer">' +
    '<textarea rows="1" placeholder="Type a message…" maxlength="2000"></textarea>' +
    '<button class="send" type="button">Send</button>' +
    "</div>" +
    '<div class="footer-note">Powered by Universal Commerce AI</div>' +
    "</div>";

  var bubbleEl = wrap.querySelector(".bubble");
  var panelEl = wrap.querySelector(".panel");
  var closeEl = wrap.querySelector(".close");
  var messagesEl = wrap.querySelector(".messages");
  var textareaEl = wrap.querySelector("textarea");
  var sendEl = wrap.querySelector(".send");

  var opened = false;
  var greeted = false;
  var sending = false;
  var conversationId = storageGet(STORAGE_KEY) || null;

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function addMessage(role, text) {
    var el = document.createElement("div");
    el.className = "msg " + role;
    el.textContent = text;
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
  }

  function addProducts(products) {
    if (!products || !products.length) return;

    var box = document.createElement("div");
    box.className = "products";

    products.slice(0, 5).forEach(function (p) {
      var name = p.name || p.title || "Product";
      var price =
        p.price !== undefined && p.price !== null
          ? typeof p.price === "number"
            ? "$" + p.price.toFixed(2)
            : String(p.price)
          : "";
      var url = p.url || p.link || "#";

      var a = document.createElement("a");
      a.className = "product";
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.innerHTML =
        '<span class="name">' +
        escapeHtml(name) +
        "</span>" +
        (price ? '<span class="price">' + escapeHtml(price) + "</span>" : "");
      box.appendChild(a);
    });

    messagesEl.appendChild(box);
    scrollToBottom();
  }

  function setSending(state) {
    sending = state;
    sendEl.disabled = state;
    textareaEl.disabled = state;
  }

  function openPanel() {
    opened = true;
    panelEl.classList.add("open");
    if (!greeted) {
      greeted = true;
      addMessage("assistant", GREETING);
    }
    textareaEl.focus();
  }

  function closePanel() {
    opened = false;
    panelEl.classList.remove("open");
  }

  bubbleEl.addEventListener("click", function () {
    opened ? closePanel() : openPanel();
  });
  closeEl.addEventListener("click", closePanel);

  textareaEl.addEventListener("input", function () {
    textareaEl.style.height = "auto";
    textareaEl.style.height = Math.min(textareaEl.scrollHeight, 90) + "px";
  });

  textareaEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  sendEl.addEventListener("click", handleSend);

  function handleSend() {
    var text = textareaEl.value.trim();
    if (!text || sending) return;

    addMessage("user", text);
    textareaEl.value = "";
    textareaEl.style.height = "auto";
    setSending(true);

    var typingEl = addMessage("typing", "…");
    typingEl.classList.add("typing");

    fetch(API_BASE + "/v1/chat", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": API_KEY,
      },
      body: JSON.stringify({
        message: text,
        conversation_id: conversationId,
      }),
    })
      .then(function (res) {
        if (res.status === 429) {
          var retryAfter = res.headers.get("Retry-After");
          throw new Error(
            "RATE_LIMIT:" + (retryAfter || "a few seconds")
          );
        }
        if (!res.ok) {
          throw new Error("HTTP_" + res.status);
        }
        return res.json();
      })
      .then(function (data) {
        typingEl.remove();

        if (data.conversation_id) {
          conversationId = data.conversation_id;
          storageSet(STORAGE_KEY, conversationId);
        }

        addMessage("assistant", data.message || "…");
        addProducts(data.products);
      })
      .catch(function (err) {
        typingEl.remove();

        var msg = "Sorry, something went wrong. Please try again.";
        if (String(err.message || "").indexOf("RATE_LIMIT:") === 0) {
          msg =
            "We're getting a lot of messages right now — please try again in " +
            err.message.split("RATE_LIMIT:")[1] +
            ".";
        }
        addMessage("error", msg);
      })
      .finally(function () {
        setSending(false);
      });
  }
})();
