/* Universal Commerce AI — optional human merchant chat mode. */
(function () {
  "use strict";

  var script = document.currentScript;
  var API_KEY = script && script.getAttribute("data-key");
  var API_BASE = ((script && script.getAttribute("data-api-base")) || location.origin).replace(/\/$/, "");
  if (!API_KEY) return;

  var CONV_KEY = "ucai_widget_conv_" + API_KEY.slice(-8);
  var VISITOR_KEY = "ucai_widget_visitor_" + API_KEY.slice(-8);
  var root = null;
  var humanMode = false;
  var sendButton = null;
  var input = null;
  var merchantButton = null;
  var modeNote = null;

  function conversationId() {
    try {
      var value = localStorage.getItem(CONV_KEY);
      if (value) return value;
      value = (crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2));
      localStorage.setItem(CONV_KEY, value);
      return value;
    } catch (_) {
      return Date.now().toString(36) + Math.random().toString(36).slice(2);
    }
  }

  function visitorId() {
    try {
      var value = localStorage.getItem(VISITOR_KEY);
      if (value) return value;
      value = (crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2));
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

  function addMessage(text, role) {
    if (!root) return;
    var messages = root.querySelector(".messages");
    if (!messages) return;
    var el = document.createElement("div");
    el.className = "msg " + (role === "user" ? "user" : "merchant");
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
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
    var originalSend = root.querySelector(".composer .send");
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

    /* Clone the send button so the existing AI click handler stays detached while
       human mode is active. The original button reference inside widget.js remains
       valid only for the detached node and cannot send an AI request. */
    var replacement = originalSend.cloneNode(true);
    originalSend.replaceWith(replacement);
    sendButton = replacement;
    sendButton.addEventListener("click", function () {
      if (humanMode) sendToMerchant();
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
})();
