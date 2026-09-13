/* Premium commerce UX layer for the standalone customer chat. */
(function () {
  "use strict";
  var products = [], language = "en", type = "", lastQuery = "", quickSignature = "";

  function lang(t) { return /[\u0980-\u09FF]/.test(String(t || "")) ? "bn" : "en"; }
  function safe(v, base) {
    if (typeof v !== "string" || !v.trim()) return "";
    try { var u = new URL(v.trim(), base || location.href); return /^https?:$/.test(u.protocol) ? u.href : ""; } catch (_) { return ""; }
  }
  function label(k) { return String(k || "").replace(/[_-]+/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }

  function attrs(p) {
    var out = [], src = p && (p.attributes || p.dynamic_attributes || p.metadata);
    var skip = { id:1,name:1,title:1,price:1,currency:1,currency_code:1,stock:1,rating:1,review_count:1,product_url:1,url:1,link:1,image_url:1,image:1,main_image:1,thumbnail:1,attributes:1,dynamic_attributes:1,metadata:1,description:1 };
    if (src && typeof src === "object" && !Array.isArray(src)) Object.keys(src).forEach(function (k) {
      var v = src[k]; if (v !== null && v !== undefined && v !== "" && typeof v !== "object") out.push([label(k), String(v)]);
    });
    Object.keys(p || {}).forEach(function (k) {
      var v = p[k]; if (skip[k] || out.length >= 5 || v === null || v === undefined || v === "" || typeof v === "object") return;
      if (/string|number|boolean/.test(typeof v)) out.push([label(k), String(v)]);
    });
    var seen = {};
    return out.filter(function (x) { var k = x[0] + "=" + x[1]; if (seen[k]) return false; seen[k] = 1; return true; }).slice(0, 3);
  }

  function style() {
    if (document.getElementById("ucai-standalone-ux")) return;
    var s = document.createElement("style"); s.id = "ucai-standalone-ux";
    s.textContent = [
      ".ucai-link{display:block;color:inherit;text-decoration:none}",
      ".ucai-link:focus-visible{outline:3px solid rgba(79,70,229,.35);outline-offset:2px;border-radius:12px}",
      ".ucai-attrs{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}",
      ".ucai-attr{font-size:10px;padding:4px 7px;border:1px solid #e7e9ee;border-radius:999px;background:#f8fafc;color:#667085}",
      ".ucai-attr b{color:#344054}",
      ".ucai-quick-replies{display:flex;gap:7px;overflow-x:auto;padding:4px 0 9px;scrollbar-width:none;max-width:100%}",
      ".ucai-quick-replies::-webkit-scrollbar{display:none}",
      ".ucai-quick{white-space:nowrap;border:1px solid #e1e4ea;background:#fff;border-radius:999px;padding:7px 11px;font-size:11px;color:#475569;cursor:pointer;box-shadow:0 2px 8px rgba(16,24,40,.04);transition:all .15s ease}",
      ".ucai-quick:hover{background:#f7f7ff;border-color:#b9b5f5;color:#4f46e5;transform:translateY(-1px)}",
      ".ucai-quick.ucai-quick-primary{background:#111827;border-color:#111827;color:#fff}",
      ".ucai-product-index{position:absolute;top:8px;left:8px;z-index:2;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:rgba(17,24,39,.76);color:#fff;font:600 10px/1 Inter,sans-serif;box-shadow:0 2px 7px rgba(0,0,0,.16)}",
      ".ucai-image-placeholder{display:flex!important;align-items:center;justify-content:center;color:#98a2b3;font-size:10px;text-align:center;padding:8px}",
      ".ucai-cleanup{display:none!important}",
      ".ucai-support-note{margin:2px 0 0;font-size:11px;color:#98a2b3}",
      ".ucai-single-welcome{margin:0!important}",
      ".ucai-single-welcome .empty-title{margin-bottom:6px}",
      "@media(max-width:560px){.ucai-quick{padding:7px 10px;font-size:10.5px}}"
    ].join("");
    document.head.appendChild(s);
  }

  function cleanupTechnicalMetadata(card) {
    var needles = ["source fingerprint", "image verified", "link নেই", "link not available", "source_fingerprint", "image_verified"];
    card.querySelectorAll("span,p,small,strong,div").forEach(function (el) {
      var text = String(el.textContent || "").trim().toLowerCase();
      if (!text || el.children.length > 0) return;
      if (needles.some(function (needle) { return text.indexOf(needle) !== -1; })) el.classList.add("ucai-cleanup");
    });
  }

  function compactWelcome() {
    var empty = document.querySelector(".empty");
    if (!empty || empty.dataset.ucaiWelcome) return;
    empty.dataset.ucaiWelcome = "1";
    empty.classList.add("ucai-single-welcome");
    var title = empty.querySelector(".empty-title");
    var copy = empty.querySelector("p:not(.empty-title)");
    var bn = language === "bn";
    if (title) title.textContent = bn ? "👋 কী খুঁজছেন?" : "👋 What are you looking for?";
    if (copy) copy.textContent = bn
      ? "পণ্যের নাম, দাম, স্টক বা ডেলিভারি সম্পর্কে জিজ্ঞেস করুন।"
      : "Ask about products, prices, stock or delivery.";
  }

  function patch() {
    style();
    compactWelcome();
    document.querySelectorAll(".product-tag").forEach(function (card, index) {
      cleanupTechnicalMetadata(card);
      if (card.dataset.ucaiUx) return;
      var nameEl = card.querySelector(".product-name"), name = nameEl ? String(nameEl.textContent || "").trim() : "";
      var a = card.querySelector("a.product-action[href]");
      var p = products.find(function (x) { return (name && String(x.name || x.title || "").trim() === name) || (a && safe(x.product_url || x.url || x.link) === a.href); });
      if (!p) return;
      card.dataset.ucaiUx = "1";
      var href = safe(p.product_url || p.url || p.link, p.product_url || p.url || location.href);

      if (!card.querySelector(".ucai-product-index")) {
        var indexBadge = document.createElement("span"); indexBadge.className = "ucai-product-index"; indexBadge.textContent = String(index + 1); indexBadge.setAttribute("aria-hidden", "true"); card.appendChild(indexBadge);
      }
      [card.querySelector(".product-thumb"), nameEl].forEach(function (el) {
        if (!el || !href || el.parentNode.closest(".ucai-link")) return;
        var link = document.createElement("a"); link.className = "ucai-link"; link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
        el.parentNode.insertBefore(link, el); link.appendChild(el);
      });

      var img = card.querySelector("img.product-thumb");
      if (img) {
        img.loading = "lazy"; img.decoding = "async"; img.alt = name || "Product image";
        img.addEventListener("error", function () {
          if (img.dataset.ucaiFallback) return;
          img.dataset.ucaiFallback = "1";
          var f = document.createElement("div"); f.className = "product-thumb product-image-fallback ucai-image-placeholder"; f.textContent = language === "bn" ? "ছবি পাওয়া যায়নি" : "Image unavailable"; img.replaceWith(f);
        });
      }
      if (a && href) a.textContent = /link|url/.test(type.toLowerCase()) ? (language === "bn" ? "পণ্য খুলুন" : "Shop now") : (language === "bn" ? "পণ্য দেখুন" : "View product");

      var pairs = attrs(p), body = card.querySelector(".product-info") || card;
      if (pairs.length && !card.querySelector(".ucai-attrs")) {
        var box = document.createElement("div"); box.className = "ucai-attrs";
        pairs.forEach(function (x) { var c = document.createElement("span"); c.className = "ucai-attr"; var b = document.createElement("b"); b.textContent = x[0] + ": "; c.appendChild(b); c.appendChild(document.createTextNode(x[1])); box.appendChild(c); });
        body.appendChild(box);
      }
    });
    quickReplies();
  }

  function normalizedQuery() {
    return String(lastQuery || "").trim().toLowerCase();
  }

  function hasAny(text, words) {
    return words.some(function (word) { return text.indexOf(word) !== -1; });
  }

  function isHumanRequest(text) {
    return hasAny(text, ["talk to merchant", "talk to a merchant", "human", "agent", "representative", "মানুষ", "মার্চেন্ট", "কথা বলতে চাই"]);
  }

  function contextualChoices() {
    var q = normalizedQuery();
    var bn = language === "bn";
    var choices;

    if (isHumanRequest(q)) {
      choices = bn ? ["মার্চেন্টের সাথে কথা বলুন", "আরেকটি প্রশ্ন"] : ["Talk to merchant", "Ask another question"];
    } else if (hasAny(q, ["delivery", "deliver", "shipping", "ship", "ডেলিভারি", "কত দিনে", "কবে পাব"])) {
      choices = bn ? ["ডেলিভারি তথ্য", "মার্চেন্টের সাথে কথা বলুন"] : ["Delivery info", "Talk to merchant"];
    } else if (hasAny(q, ["warranty", "guarantee", "ওয়ারেন্টি", "ওয়্যারেন্টি", "গ্যারান্টি"])) {
      choices = bn ? ["ওয়ারেন্টি তথ্য", "মার্চেন্টের সাথে কথা বলুন"] : ["Warranty info", "Talk to merchant"];
    } else if (hasAny(q, ["return", "refund", "exchange", "ফেরত", "রিটার্ন", "রিফান্ড", "এক্সচেঞ্জ"])) {
      choices = bn ? ["রিটার্ন পলিসি", "মার্চেন্টের সাথে কথা বলুন"] : ["Return policy", "Talk to merchant"];
    } else if (hasAny(q, ["compare", "comparison", "তুলনা", "vs ", " vs"])) {
      choices = bn ? ["তুলনা করুন", "বিস্তারিত"] : ["Compare", "Details"];
    } else if (hasAny(q, ["price", "cost", "দাম", "মূল্য", "কত টাকা", "কতো টাকা"])) {
      choices = bn ? ["কম দামের অপশন", "আরও দেখুন"] : ["Lower price", "Show more"];
    } else if (hasAny(q, ["detail", "details", "tell me more", "বিস্তারিত", "জানতে চাই"])) {
      choices = bn ? ["বিস্তারিত", "ছবি দেখুন"] : ["More details", "Show photos"];
    } else if (hasAny(q, ["stock", "available", "availability", "আছে", "স্টকে", "স্টক"])) {
      choices = bn ? ["স্টকে আছে এমন", "কম দামের অপশন"] : ["In stock", "Lower price"];
    } else {
      choices = bn ? ["আরও দেখান", "কম দামের অপশন", "স্টকে আছে এমন"] : ["Show more", "Lower price", "In stock"];
    }

    return choices.slice(0, 3);
  }

  function sendQuickReply(text) {
    var input = document.querySelector("#message-input") || document.querySelector("textarea");
    if (!input) return;
    var composer = input.closest("form");
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles:true }));
    input.focus();
    if (composer && /talk to merchant|মার্চেন্টের সাথে কথা বলুন/i.test(text)) {
      setTimeout(function () { if (typeof composer.requestSubmit === "function") composer.requestSubmit(); }, 0);
    }
  }

  function quickReplies() {
    var composerInput = document.querySelector("#message-input") || document.querySelector("textarea");
    var composer = composerInput && composerInput.closest("form");
    if (!composer) return;

    var choices = contextualChoices();
    var signature = language + "|" + type + "|" + normalizedQuery() + "|" + choices.join("|");
    if (quickSignature === signature && document.querySelector(".ucai-quick-replies")) return;
    quickSignature = signature;

    document.querySelectorAll(".ucai-quick-replies").forEach(function (el) { el.remove(); });
    var box = document.createElement("div"); box.className = "ucai-quick-replies"; box.setAttribute("aria-label", "Suggested questions");
    choices.forEach(function (text, index) {
      var b = document.createElement("button"); b.type = "button"; b.className = "ucai-quick" + ((/talk to merchant|মার্চেন্টের সাথে কথা বলুন/i.test(text)) ? " ucai-quick-primary" : ""); b.textContent = text;
      b.addEventListener("click", function () { sendQuickReply(text); });
      box.appendChild(b);
    });
    composer.parentNode.insertBefore(box, composer);
  }

  var nativeFetch = window.fetch;
  window.fetch = function () {
    var args = arguments, u = String(args[0] && args[0].url ? args[0].url : args[0] || ""), o = args[1] || {};
    try {
      if (u.indexOf("/v1/chat") !== -1 && o.body) {
        var b = JSON.parse(o.body);
        if (b.message) { lastQuery = String(b.message); language = lang(b.message); quickSignature = ""; }
      }
    } catch (_) {}
    return nativeFetch.apply(this, args).then(function (r) {
      if (u.indexOf("/v1/chat") !== -1 || u.indexOf("/v1/images/") !== -1) r.clone().json().then(function (d) {
        if (d) {
          if (Array.isArray(d.products)) products = d.products;
          type = String(d.type || d.intent || "");
          if (d.message && !lastQuery) language = lang(d.message);
          setTimeout(patch, 0);
        }
      }).catch(function () {});
      return r;
    });
  };

  document.addEventListener("input", function (e) {
    if (e.target && (e.target.id === "message-input" || e.target.tagName === "TEXTAREA")) {
      lastQuery = String(e.target.value || "");
      language = lang(lastQuery);
      quickSignature = "";
      setTimeout(quickReplies, 0);
    }
  });

  new MutationObserver(patch).observe(document.body, { childList:true, subtree:true });
  patch();
})();
