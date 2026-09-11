/* Universal Commerce AI — customer-to-merchant chat bridge. */
(function () {
  "use strict";

  var script = document.currentScript || document.scripts[document.scripts.length - 1];
  var API_KEY = script && script.getAttribute("data-key");
  var API_BASE = ((script && script.getAttribute("data-api-base")) || location.origin).replace(/\/$/, "");
  if (!API_KEY) return;

  var PREFIX = "ucai_widget_" + API_KEY.slice(-8);
  var CONV_KEY = PREFIX + "_conv";
  var TOKEN_KEY = PREFIX + "_conv_token";
  var VISITOR_KEY = PREFIX + "_visitor";
  var POLL_KEY = PREFIX + "_merchant_poll";

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

  function storageGet(key) {
    try { return localStorage.getItem(key) || ""; } catch (_) { return ""; }
  }

  function getConversation() { return storageGet(CONV_KEY); }
  function getToken() { return storageGet(TOKEN_KEY); }

  function getVisitor() {
    var value = storageGet(VISITOR_KEY);
    if (value) return value;
    value = makeId();
    try { localStorage.setItem(VISITOR_KEY, value); } catch (_) {}
    return value;
  }

  function authHeaders(extra) {
    var headers = extra || {};
    var token = getToken();
    if (token) headers["x-conversation-token"] = token;
    return headers;
  }

  function findWidgetRoot() {
    var nodes = document.body ? document.body.children : [];
    for (var i = 0; i < nodes.length; i++) {
      var shadow = nodes[i].shadowRoot;
      if (shadow && shadow.querySelector(".panel") && shadow.querySelector(".composer")) return shadow;
    }
    return null;
  }

  function hasConversation() { return !!getConversation() && !!getToken(); }

  function addMessage(text, role, messageId) {
    if (!root) return;
    var messages = root.querySelector(".messages");
    if (!messages) return;
    if (messageId) {
      var existing = root.querySelector('[data-merchant-message-id="' + CSS.escape(String(messageId)) + '"]');
      if (existing) return;
    }
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
      method: "GET",
      headers: authHeaders({ "x-api-key": API_KEY })
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          var error = new Error((data && data.detail) || ("HTTP " + response.status));
          error.status = response.status;
          throw error;
        });
      }
      return response.json();
    });
  }

  function renderMode(enabled) {
    humanMode = !!enabled;
    if (!root || !merchantButton || !input) return;
    merchantButton.textContent = humanMode ? "🤖 AI assistant" : "💬 Talk to merchant";
    merchantButton.setAttribute("aria-pressed", humanMode ? "true" : "false");
    merchantButton.style.background = humanMode ? "#ecfdf5" : "#fff";
    merchantButton.style.color = humanMode ? "#047857" : "#475569";
    input.placeholder = humanMode ? "Write a message to the merchant…" : "পণ্য, দাম বা product link সম্পর্কে জিজ্ঞেস করুন…";
    if (modeNote) {
      modeNote.textContent = humanMode ? "You are chatting with the merchant. AI auto-replies are paused." : "AI assistant mode";
      modeNote.style.display = humanMode ? "block" : "none";
    }
    if (humanMode) startMerchantPolling(); else stopMerchantPolling();
  }

  function syncModeFromServer() {
    if (!hasConversation()) return;
    fetchCustomerState().then(function (data) {
      if (!data || (data.mode !== "human" && data.mode !== "ai")) return;
      if (data.mode === "human" && data.mode_owner === "merchant") {
        renderMode(true);
        return;
      }
      renderMode(data.mode === "human");
    }).catch(function (error) {
      if (error && (error.status === 401 || error.status === 403)) {
        try { localStorage.removeItem(TOKEN_KEY); } catch (_) {}
        renderMode(false);
      }
    });
  }

  function startModePolling() {
    syncModeFromServer();
    if (modePollingTimer) return;
    modePollingTimer = setInterval(syncModeFromServer, 4000);
  }

  function stopModePolling() {
    if (modePollingTimer) { clearInterval(modePollingTimer); modePollingTimer = null; }
  }

  function pollMerchantMessages() {
    fetchCustomerState().then(function (data) {
      if (!data) return;
      if (data.mode === "human" && !humanMode) renderMode(true);
      if (data.mode !== "human" && humanMode && data.mode_owner !== "merchant") renderMode(false);
      if (!humanMode || !Array.isArray(data.messages)) return;

      var merchantMessages = data.messages.filter(function (message) {
        return message && message.role === "merchant" && message.id != null;
      });
      for (var i = 0; i < merchantMessages.length; i++) {
        var message = merchantMessages[i];
        if (!lastMerchantMessageId || String(message.id) !== String(lastMerchantMessageId)) {
          if (!root.querySelector('[data-merchant-message-id="' + CSS.escape(String(message.id)) + '"]')) {
            addMessage("Store team: " + (message.content || ""), "merchant", message.id);
          }
        }
      }
      if (merchantMessages.length) {
        lastMerchantMessageId = String(merchantMessages[merchantMessages.length - 1].id);
        try { localStorage.setItem(POLL_KEY, JSON.stringify({ conversation_id: getConversation(), last_id: lastMerchantMessageId })); } catch (_) {}
      }
    }).catch(function (error) {
      if (error && (error.status === 401 || error.status === 403)) stopMerchantPolling();
    });
  }

  function startMerchantPolling() {
    if (!hasConversation()) return;
    var conversation = getConversation();
    if (initializedConversation !== conversation) {
      initializedConversation = conversation;
      lastMerchantMessageId = null;
      try {
        var stored = JSON.parse(localStorage.getItem(POLL_KEY) || "null");
        if (stored && stored.conversation_id === conversation && stored.last_id != null) lastMerchantMessageId = String(stored.last_id);
      } catch (_) {}
    }
    pollMerchantMessages();
    if (!pollingTimer) pollingTimer = setInterval(pollMerchantMessages, 4000);
  }

  function stopMerchantPolling() {
    if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; }
  }

  function setRemoteMode(mode) {
    var conversation = getConversation();
    var token = getToken();
    if (!conversation || !token) return Promise.reject(new Error("No authenticated conversation"));
    return fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversation) + "/mode", {
      method: "POST",
      headers: authHeaders({ "content-type": "application/json", "x-api-key": API_KEY }),
      body: JSON.stringify({ mode: mode })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var error = new Error((data && data.detail) || ("HTTP " + response.status));
          error.status = response.status;
          throw error;
        }
        return data;
      });
    });
  }

  function setMode(enabled) {
    if (modeChanging || enabled === humanMode) return;
    if (!hasConversation()) {
      addMessage("Please send one message first. Then you can talk directly with the merchant.", "merchant");
      if (input) input.focus();
      return;
    }

    modeChanging = true;
    var previous = humanMode;
    renderMode(enabled);
    setRemoteMode(enabled ? "human" : "ai").then(function (data) {
      renderMode(data && data.mode === "human");
    }).catch(function (error) {
      renderMode(previous);
      var detail = error && error.message ? error.message : "Could not change chat mode.";
      addMessage(detail === "Could not change chat mode." ? detail + " Please try again." : detail, "merchant");
      console.error("Merchant chat mode error:", error);
    }).finally(function () { modeChanging = false; });
  }

  function sendToMerchant() {
    var text = (input && input.value || "").trim();
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
        if (!response.ok) {
          var error = new Error((data && data.detail) || ("HTTP " + response.status));
          error.status = response.status;
          throw error;
        }
        return data;
      });
    }).then(function () {
      addMessage(text, "user");
      input.value = "";
      input.style.height = "auto";
      renderMode(true);
      startMerchantPolling();
    }).catch(function (error) {
      addMessage((error && error.message) || "Message could not be sent. Please try again.", "merchant");
      console.error("Merchant chat error:", error);
    }).finally(function () {
      sendButton.disabled = false;
      input.focus();
    });
  }

  function install() {
    root = findWidgetRoot();
    if (!root) return false;
    if (root.querySelector(".merchant-chat-button")) {
      merchantButton = root.querySelector(".merchant-chat-button");
      input = root.querySelector(".composer textarea");
      sendButton = root.querySelector(".composer .send");
      return !!merchantButton && !!input && !!sendButton;
    }

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
    var composer = root.querySelector(".composer");
    if (composer) composer.before(modeNote);

    merchantButton.addEventListener("click", function () {
      if (!modeChanging && humanMode) {
        setMode(false);
        return;
      }
      setMode(true);
    });

    var replacement = originalSend.cloneNode(true);
    originalSend.replaceWith(replacement);
    sendButton = replacement;
    sendButton.addEventListener("click", function () {
      if (humanMode) sendToMerchant();
      else replacement.__ucaiNativeSend && replacement.__ucaiNativeSend();
    });
    replacement.__ucaiNativeSend = function () { if (typeof originalSend.onclick === "function") originalSend.onclick(); };

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
  (function waitForWidget() {
    if (install()) return;
    if (++attempts < 160) setTimeout(waitForWidget, 100);
  })();

  window.addEventListener("beforeunload", function () {
    stopMerchantPolling();
    stopModePolling();
  });
})();
