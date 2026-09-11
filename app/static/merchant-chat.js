/* Universal Commerce AI — optional human merchant chat mode. */
(function () {
  "use strict";

  var script = document.currentScript;
  var API_KEY = script && script.getAttribute("data-key");
  var API_BASE = ((script && script.getAttribute("data-api-base")) || location.origin).replace(/\/$/, "");
  if (!API_KEY) return;

  var CONV_KEY = "ucai_widget_conv_" + API_KEY.slice(-8);
  var VISITOR_KEY = "ucai_widget_visitor_" + API_KEY.slice(-8);
  var POLL_KEY = "ucai_widget_merchant_poll_" + API_KEY.slice(-8);
  var root = null;
  var humanMode = false;
  var sendButton = null;
  var originalSend = null;
  var input = null;
  var merchantButton = null;
  var modeNote = null;
  var pollingTimer = null;
  var lastMerchantMessageId = null;
  var initializedConversation = null;

  function makeId() {
    try {
      if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    } catch (_) {}
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function conversationId() {
    try {
      var value = localStorage.getItem(CONV_KEY);
      if (value) return value;
      value = makeId();
      localStorage.setItem(CONV_KEY, value);
      return value;
    } catch (_) {
      return makeId();
    }
  }

  function visitorId() {
    try {
      var value = localStorage.getItem(VISITOR_KEY);
      if (value) return value;
      value = makeId();
      localStorage.setItem(VISITOR_KEY, value);
      return value;
    } catch (_) {
      return "anonymous";
    }
  }

  function findRoot() {
    var nodes = document.body ? document.body.children : [];
    for (var i = 0; i < nodes.length; i++) {
      var r = nodes[i].shadowRoot;
      if (r && r.querySelector(".panel") && r.querySelector(".composer textarea")) return r;
    }
    return null;
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
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function pollMerchantMessages() {
    if (!humanMode) return;
    var conversation = conversationId();
    fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversation), {
      headers: { "x-api-key": API_KEY }
    })
      .then(function (response) {
        if (!response.ok) return null;
        return response.json();
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.messages)) return;

        var merchantMessages = data.messages.filter(function (message) {
          return message && message.role === "merchant" && message.id;
        });
        if (!merchantMessages.length) return;

        var startIndex = 0;
        if (lastMerchantMessageId !== null) {
          var foundIndex = -1;
          for (var i = 0; i < merchantMessages.length; i++) {
            if (String(merchantMessages[i].id) === String(lastMerchantMessageId)) {
              foundIndex = i;
              break;
            }
          }
          if (foundIndex >= 0) startIndex = foundIndex + 1;
        }

        for (var j = startIndex; j < merchantMessages.length; j++) {
          var message = merchantMessages[j];
          if (!hasRenderedMerchantMessage(message.id)) {
            addMessage("Store team: " + (message.content || ""), "merchant", message.id);
          }
        }

        lastMerchantMessageId = String(merchantMessages[merchantMessages.length - 1].id);
        try {
          localStorage.setItem(POLL_KEY, JSON.stringify({
            conversation_id: conversation,
            last_id: lastMerchantMessageId
          }));
        } catch (_) {}
      })
      .catch(function () {});
  }

  function startMerchantPolling() {
    var conversation = getConversation();
    if (initializedConversation !== conversation) {
      initializedConversation = conversation;
      lastMerchantMessageId = null;
      try {
        var stored = JSON.parse(localStorage.getItem(POLL_KEY) || "null");
        if (stored && stored.conversation_id === conversation && stored.last_id) {
          lastMerchantMessageId = String(stored.last_id);
        }
      } catch (_) {}
    }
    pollMerchantMessages();
    if (pollingTimer) return;
    pollingTimer = setInterval(pollMerchantMessages, 4000);
  }

  function stopMerchantPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
  }

  function setMode(enabled) {
    humanMode = enabled;
    if (!root) return;
    merchantButton.textContent = enabled ? "🤖 AI assistant" : "💬 Talk to merchant";
    merchantButton.setAttribute("aria-pressed", enabled ? "true" : "false");
    merchantButton.style.background = enabled ? "#ecfdf5" : "#fff";
    merchantButton.style.color = enabled ? "#047857" : "#475569";
    input.placeholder = enabled ? "Write a message to the merchant…" : "পণ্য, দাম বা product link সম্পর্কে জিজ্ঞেস করুন…";
    if (modeNote) {
      modeNote.textContent = enabled ? "You are chatting with the merchant. Replies will appear here." : "AI assistant mode";
      modeNote.style.display = enabled ? "block" : "none";
    }
    if (enabled) startMerchantPolling();
    else stopMerchantPolling();
  }

  function sendToMerchant() {
    var text = (input.value || "").trim();
    if (!text) return;
    var conversation = conversationId();
    var visitor = visitorId();
    sendButton.disabled = true;
    fetch(API_BASE + "/v1/messages/customer/" + encodeURIComponent(conversation), {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": API_KEY },
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
      if (humanMode) input.focus();
    });

    /* Keep the original AI button and its listener detached. The replacement
       delegates to it whenever the customer returns to AI mode. */
    var replacement = originalSend.cloneNode(true);
    originalSend.replaceWith(replacement);
    sendButton = replacement;
    sendButton.addEventListener("click", function () {
      if (humanMode) sendToMerchant();
      else originalSend.click();
    });

    /* Enter normally belongs to the AI widget. Capture it only in human mode. */
    input.addEventListener("keydown", function (event) {
      if (humanMode && event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        event.stopImmediatePropagation();
        sendToMerchant();
      }
    }, true);

    setMode(false);
    return true;
  }

  var attempts = 0;
  (function wait() {
    if (install()) return;
    if (++attempts < 80) setTimeout(wait, 100);
  })();

  window.addEventListener("beforeunload", stopMerchantPolling);
})();