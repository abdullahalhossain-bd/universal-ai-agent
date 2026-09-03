/* Merchant-reply bridge for the customer chat UI. Polls only the current conversation. */
(function () {
  "use strict";
  var API_BASE = window.location.origin;
  var KEY_STORAGE = "uai_chat_key";
  var PREFIX = "uai_chat_convo_";
  var seen = {};

  function escapeText(value) { return value == null ? "" : String(value); }

  function renderMerchantMessage(text) {
    var thread = document.getElementById("thread");
    if (!thread) return;
    var wrap = document.createElement("div");
    wrap.className = "msg msg-assistant";
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = escapeText(text);
    wrap.appendChild(bubble);
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  function poll() {
    var key = null, conversationId = null;
    try {
      key = localStorage.getItem(KEY_STORAGE);
      conversationId = key && localStorage.getItem(PREFIX + key);
    } catch (e) {}
    if (!key || !conversationId) return;

    fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversationId), {
      headers: { "x-api-key": key }
    }).then(function (res) { return res.ok ? res.json() : null; }).then(function (data) {
      if (!data || !Array.isArray(data.messages)) return;
      data.messages.forEach(function (message) {
        if (message.role !== "merchant" || seen[message.id]) return;
        seen[message.id] = true;
        renderMerchantMessage(message.content);
      });
    }).catch(function () {});
  }

  setInterval(poll, 3000);
  poll();
})();
