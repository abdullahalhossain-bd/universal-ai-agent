/* Universal Commerce AI — conversation history + merchant reply bridge.
 *
 * The standalone customer chat already renders the current turn locally.
 * This bridge hydrates the persisted conversation after reload, then polls
 * only for genuinely new merchant replies. It never replaces or duplicates
 * the customer's own questions and assistant replies.
 *
 * Auth contract (must match app/api/routes/messages.py):
 * - Customer endpoints require BOTH the public API key (x-api-key) AND the
 *   per-conversation secret (x-conversation-token, stored by app.js as
 *   uai_chat_token_<key>). The merchant inbox endpoints under
 *   /v1/messages/conversations/* require a merchant session and can never
 *   be called from here.
 */
(function () {
  "use strict";

  var API_BASE = window.location.origin;
  var KEY_STORAGE = "uai_chat_key";
  var TOKEN_PREFIX = "uai_chat_token_";
  var PREFIX = "uai_chat_convo_";
  var seen = {};
  var hydratedConversation = null;
  var pollTimer = null;
  var consecutiveAuthFailures = 0;

  function text(value) {
    return value == null ? "" : String(value);
  }

  function renderMessage(role, content) {
    var thread = document.getElementById("thread");
    if (!thread || !content) return;

    var wrap = document.createElement("div");
    wrap.className = "msg msg-" + (role === "user" ? "user" : "assistant");
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text(content);
    wrap.appendChild(bubble);
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  function getCredentials() {
    var key = null;
    var conversationId = null;
    var token = null;
    try {
      key = localStorage.getItem(KEY_STORAGE);
      conversationId = key && localStorage.getItem(PREFIX + key);
      token = key && localStorage.getItem(TOKEN_PREFIX + key);
    } catch (e) {}
    return { key: key, conversationId: conversationId, token: token };
  }

  function customerHeaders(credentials) {
    var headers = { "x-api-key": credentials.key };
    if (credentials.token) headers["x-conversation-token"] = credentials.token;
    return headers;
  }

  function handleAuthFailure(res) {
    if (res && (res.status === 401 || res.status === 403)) {
      // The conversation token was revoked (or the conversation removed):
      // stop polling instead of hammering the API forever.
      consecutiveAuthFailures += 1;
      if (consecutiveAuthFailures >= 2) stopPolling();
      return true;
    }
    consecutiveAuthFailures = 0;
    return false;
  }

  function fetchConversation(credentials) {
    return fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(credentials.conversationId), {
      headers: customerHeaders(credentials)
    }).then(function (res) {
      if (handleAuthFailure(res)) return null;
      return res.ok ? res.json() : null;
    });
  }

  function hydrate() {
    var credentials = getCredentials();
    if (!credentials.key || !credentials.conversationId) return Promise.resolve();

    return fetchConversation(credentials).then(function (data) {
      if (!data || !Array.isArray(data.messages)) return;

      hydratedConversation = credentials.conversationId;
      data.messages.forEach(function (message) {
        if (!message || !message.id || seen[message.id]) return;
        seen[message.id] = true;
        // The customer endpoint exposes assistant/merchant replies (the
        // customer's own messages are out of scope for this endpoint).
        if (message.role === "assistant" || message.role === "merchant") {
          renderMessage(message.role, message.content);
        }
      });
    }).catch(function () {});
  }

  function pollMerchantReplies() {
    var credentials = getCredentials();
    if (!credentials.key || !credentials.conversationId) return;
    if (hydratedConversation && hydratedConversation !== credentials.conversationId) {
      seen = {};
      hydratedConversation = null;
      hydrate();
      return;
    }

    fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(credentials.conversationId), {
      headers: customerHeaders(credentials)
    }).then(function (res) {
      if (handleAuthFailure(res)) return null;
      return res.ok ? res.json() : null;
    }).then(function (data) {
      if (!data || !Array.isArray(data.messages)) return;
      data.messages.forEach(function (message) {
        if (!message || message.role !== "merchant" || seen[message.id]) return;
        seen[message.id] = true;
        renderMessage("merchant", message.content);
      });
    }).catch(function () {});
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  hydrate().then(function () {
    if (pollTimer) return;
    pollTimer = setInterval(pollMerchantReplies, 3000);
    pollMerchantReplies();
  });
  window.addEventListener("beforeunload", stopPolling);
})();
