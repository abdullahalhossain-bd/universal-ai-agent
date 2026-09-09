/* Universal Commerce AI — conversation history + merchant reply bridge.
 *
 * The standalone customer chat already renders the current turn locally.
 * This bridge hydrates the persisted conversation after reload, then polls
 * only for genuinely new merchant replies. It never replaces or duplicates
 * the customer's own questions and assistant replies.
 */
(function () {
  "use strict";

  var API_BASE = window.location.origin;
  var KEY_STORAGE = "uai_chat_key";
  var PREFIX = "uai_chat_convo_";
  var seen = {};
  var hydratedConversation = null;

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
    try {
      key = localStorage.getItem(KEY_STORAGE);
      conversationId = key && localStorage.getItem(PREFIX + key);
    } catch (e) {}
    return { key: key, conversationId: conversationId };
  }

  function fetchConversation(key, conversationId) {
    return fetch(API_BASE + "/v1/messages/conversations/" + encodeURIComponent(conversationId), {
      headers: { "x-api-key": key }
    }).then(function (res) {
      return res.ok ? res.json() : null;
    });
  }

  function hydrate() {
    var credentials = getCredentials();
    if (!credentials.key || !credentials.conversationId) return Promise.resolve();

    return fetchConversation(credentials.key, credentials.conversationId).then(function (data) {
      if (!data || !Array.isArray(data.messages)) return;

      hydratedConversation = credentials.conversationId;
      data.messages.forEach(function (message) {
        if (!message || !message.id || seen[message.id]) return;
        seen[message.id] = true;
        if (message.role === "user" || message.role === "assistant" || message.role === "merchant") {
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
      headers: { "x-api-key": credentials.key }
    }).then(function (res) {
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

  hydrate().then(function () {
    setInterval(pollMerchantReplies, 3000);
    pollMerchantReplies();
  });
})();
