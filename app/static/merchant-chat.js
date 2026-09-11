/* Universal Commerce AI — customer-to-merchant chat bridge. */
(function () {
  "use strict";

  var script = document.currentScript;
  var API_KEY = script && script.getAttribute("data-key");
  var API_BASE = ((script && script.getAttribute("data-api-base")) || location.origin).replace(/\/$/, "");
  if (!API_KEY) return;

  /* Share the exact conversation/token storage used by widget.js. */
  var PREFIX = "ucai_widget_" + API_KEY.slice(-8);
  var CONV_KEY = PREFIX + "_conv";
  var TOKEN_KEY = PREFIX + "_conv_token";
  var VISITOR_KEY = PREFIX + "_visitor";
  var POLL_KEY = PREFIX + "_merchant_poll";
  var MODE_POLL_KEY = PREFIX + "_mode_poll";

  var root = null;
  var humanMode = false;
  var sendButton = null;
  var originalSend = null;
  var input = null;
  var merchantButton = null;
  var modeNote = null;
  var pollingTimer = null;
  var modePollingTimer = null;
  var lastMerchantMessageId = null;
  var initializedConversation = null;
  var modeChanging = false;

  function makeId() {
    try { if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID(); } catch (_) {}
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function getConversation() {
    try { return localStorage.getItem(CONV_KEY) || ""; } catch (_) { return ""; }
  }

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (_) { return ""; }
  }

  function getVisitor() {
    try {
      var value = localStorage.getItem(VISITOR_KEY);
      if (value) return value;
      value = makeId();
      localStorage.setItem(VISITOR_KEY, value);
      return value;
    } catch (_) { return "anonymous"; }
  }

  function authHeaders(extra) {
    var headers = extra || {};
    var token = getToken();
    if (token) headers["x-conversation-token"] = token;
    return headers;
  }

  function hasConversation() {
    return !!getConversation() && !!getToken();
  }

  function hasRenderedMerchantMessage(messageId) {
    if (!root || !messageId) return false;
    var nodes = root.querySelectorAll("[data-merchant-message-id]");
    var wanted = String(messageId);
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getAttribute("data-merchant-message-id") === wanted) return true;
    }
    return false;
  }

  function addMessage(text, role, messageId) {
    if (!root) return;
    var messages = root.querySelector(".messages");
    if (!messages) return;
    if (messageId && hasRenderedMerchantMessage(messageId)) return;
    var el = document.createElement("div");
    el.className = "msg " + (role === "user" ? "user" : "merchant");
    if (messageId) el.setAttribute("data-merchant-message-id", String(messageId));
    el.textContent = text || "";
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function fetchCustomerState() {
    var conversation = getConversation();
    var token = getToken();
    if (!conversation || !token) return Promise.resolve(null);
    return fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversation), {
      headers: authHeaders({ "x-api-key": API_KEY })
    }).then(function (response) {
      if (response.status === 401 || response.status === 403) return null;
      if (!response.ok) return null;
      return response.json();
    });
  }

  function pollMerchantMessages() {
    fetchCustomerState().then(function (data) {
      if (!data) return;
      if (data.mode === "human" && !humanMode) renderMode(true);
      else if (data.mode === "ai" && humanMode && data.mode_owner !== "merchant") renderMode(false);
      if (!humanMode || !Array.isArray(data.messages)) return;

      var merchantMessages = data.messages.filter(function (message) {
        return message && message.role === "merchant" && message.id;
      });
      if (!merchantMessages.length) return;

      var startIndex = 0;
      if (lastMerchantMessageId !== null) {
        var foundIndex = -1;
        for (var i = 0; i < merchantMessages.length; i++) {
          if (String(merchantMessages[i].id) === String(lastMerchantMessageId)) { foundIndex = i; break; }
        }
        if (foundIndex >= 0) startIndex = foundIndex + 1;
      }

      for (var j = startIndex; j < merchantMessages.length; j++) {
        var message = merchantMessages[j];
        if (!hasRenderedMerchantMessage(message.id)) addMessage("Store team: " + (message.content || ""), "merchant", message.id);
      }

      lastMerchantMessageId = String(merchantMessages[merchantMessages.length - 1].id);
      try { localStorage.setItem(POLL_KEY, JSON.stringify({ conversation_id: getConversation(), last_id: lastMerchantMessageId })); } catch (_) {}
    }).catch(function () {});
  }

  function startMerchantPolling() {
    if (!hasConversation()) return;
    var conversation = getConversation();
    if (initializedConversation !== conversation) {
      initializedConversation = conversation;
      lastMerchantMessageId = null;
      try {
        var stored = JSON.parse(localStorage.getItem(POLL_KEY) || "null");
        if (stored && stored.conversation_id === conversation && stored.last_id) lastMerchantMessageId = String(stored.last_id);
      } catch (_) {}
    }
    pollMerchantMessages();
    if (pollingTimer) return;
    pollingTimer = setInterval(pollMerchantMessages, 4000);
  }

  function stopMerchantPolling() {
    if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; }
  }

  function syncModeFromServer() {
    fetchCustomerState().then(function (data) {
      if (!data || (data.mode !== "human" && data.mode !== "ai")) return;
      renderMode(data.mode === "human");
    }).catch(function () {});
  }

  function startModePolling() {
    syncModeFromServer();
    if (modePollingTimer) return;
    modePollingTimer = setInterval(syncModeFromServer, 4000);
  }

  function stopModePolling() {
    if (modePollingTimer) { clearInterval(modePollingTimer); modePollingTimer = null; }
  }

  function renderMode(enabled) {
    humanMode = enabled;
    if (!root || !merchantButton || !input) return;
    merchantButton.textContent = enabled ? "🤖 AI assistant" : "💬 Talk to merchant";
    merchantButton.setAttribute("aria-pressed", enabled ? "true" : "false");
    merchantButton.style.background = enabled ? "#ecfdf5" : "#fff";
    merchantButton.style.color = enabled ? "#047857" : "#475569";
    input.placeholder = enabled ? "Write a message to the merchant…" : "পণ্য, দাম বা product link সম্পর্কে জিজ্ঞেস করুন…";
    if (modeNote) {
      modeNote.textContent = enabled ? "You are chatting with the merchant. AI auto-replies are paused." : "AI assistant mode";
      modeNote.style.display = enabled ? "block" : "none";
    }
    if (enabled) startMerchantPolling(); else stopMerchantPolling();
  }

  function setRemoteMode(mode) {
    var conversation = getConversation();
    var token = getToken();
    if (!conversation || !token) return Promise.reject(new Error("Start a chat first so the conversation can be securely connected."));
    return fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversation) + "/mode", {
      method: "POST",
      headers: authHeaders({ "content-type": "application/json", "x-api-key": API_KEY }),
      body: JSON.stringify({ mode: mode })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
        return data;
      });
    });
  }

  function setMode(enabled) {
    if (modeChanging || enabled === humanMode) return;
    if (!hasConversation()) {
      addMessage("Please send one message first. Then you can talk directly with the merchant.", "merchant");
      input.focus();
      return;
    }
    modeChanging = true;
    var previous = humanMode;
    renderMode(enabled);
    setRemoteMode(enabled ? "human" : "ai").catch(function (error) {
      renderMode(previous);
      addMessage("Could not connect to the merchant. Please try again.", "merchant");
      console.error("Merchant chat mode error:", error);
    }).finally(function () { modeChanging = false; });
  }

  function sendToMerchant() {
    var text = (input.value || "").trim();
    if (!text || !hasConversation()) return;
    var conversation = getConversation();
    var visitor = getVisitor();
    sendButton.disabled = true;
    fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversation), {
      method: "POST",
      headers: authHeaders({ "content-type": "application/json", "x-api-key": API_KEY }),
      body: JSON.stringify({ message: text, visitor_id: visitor })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
        return data;
      });
    }).then(function () {
      addMessage(text, "user");
      input.value = "";
      input.style.height = "auto";
      renderMode(true);
      startMerchantPolling();
    }).catch(function (error) {
      addMessage("Message could not be sent. Please try again.", "merchant");
      console.error("Merchant chat error:", error);
    }).finally(function () {
      sendButton.disabled = false;
      input.focus();
    });
  }

  function install() {
    root = findRoot();
    if (!root || root.querySelector(".merchant-chat-button")) return !!root;
    input = root.querySelector(".composer textarea");
    originalSend = root.querySelector(".composer .send");
    var tools = root.querySelector(".tools");
    if (!input || !originalSend || !tools) return false;

    merchantButton = document.createElement("button");
    merchantButton.type = "button";
    merchantButton.className = "tool merchant-chat-button";
    merchantButton.setAttribute("aria-pressed", "false");
    merchantButton.textContent = "💬 Talk to merchant";
    merchantButton.title = "Chat directly with the merchant";
    tools.appendChild(merchantButton);

    modeNote = document.createElement("div");
    modeNote.style.cssText = "display:none;padding:5px 10px 0;background:#fff;color:#047857;font-size:10.5px";
    root.querySelector(".composer").before(modeNote);

    merchantButton.addEventListener("click", function () {
      setMode(!humanMode);
      if (!modeChanging && humanMode) input.focus();
    });

    var replacement = originalSend.cloneNode(true);
    originalSend.replaceWith(replacement);
    sendButton = replacement;
    sendButton.addEventListener("click", function () {
      if (humanMode) sendToMerchant();
      else originalSend.click();
    });

    input.addEventListener("keydown", function (event) {
      if (humanMode && event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        event.stopImmediatePropagation();
        sendToMerchant();
      }
    }, true);

    renderMode(false);
    startModePolling();
    return true;
  }

  var attempts = 0;
  (function wait() {
    if (install()) return;
    if (++attempts < 80) setTimeout(wait, 100);
  })();

  window.addEventListener("beforeunload", function () {
    stopMerchantPolling();
    stopModePolling();
  });
})();
