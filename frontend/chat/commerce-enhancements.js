/* Premium commerce UX layer for the standalone customer chat. */
(function () {
  "use strict";
  var products = [], language = "en", type = "";

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
      ".ucai-quick-replies{display:flex;gap:7px;overflow-x:auto;padding:4px 0 9px;scrollbar-width:none}",
      ".ucai-quick-replies::-webkit-scrollbar{display:none}",
      ".ucai-quick{white-space:nowrap;border:1px solid #e1e4ea;background:#fff;border-radius:999px;padding:7px 11px;font-size:11px;color:#475569;cursor:pointer;box-shadow:0 2px 8px rgba(16,24,40,.04);transition:all .15s ease}",
      ".ucai-quick:hover{background:#f7f7ff;border-color:#b9b5f5;color:#4f46e5;transform:translateY(-1px)}",
      ".ucai-product-index{position:absolute;top:8px;left:8px;z-index:2;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:rgba(17,24,39,.76);color:#fff;font:600 10px/1 Inter,sans-serif;box-shadow:0 2px 7px rgba(0,0,0,.16)}",
      ".ucai-image-placeholder{display:flex!important;align-items:center;justify-content:center;color:#98a2b3;font-size:10px;text-align:center;padding:8px}",
      ".ucai-cleanup{display:none!important}",
      ".ucai-support-note{margin:2px 0 0;font-size:11px;color:#98a2b3}"
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

  function patch() {
    style();
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

  function quickReplies() {
    if (document.querySelector(".ucai-quick-replies")) return;
    var composer = document.querySelector("textarea") && document.querySelector("textarea").closest("form"); if (!composer) return;
    var box = document.createElement("div"); box.className = "ucai-quick-replies";
    var choices = language === "bn" ? ["আরও দেখান", "কম দামের অপশন", "স্টকে আছে এমন", "বিস্তারিত বলুন"] : ["Show more", "Lower price", "In stock", "Tell me more"];
    choices.forEach(function (text) { var b = document.createElement("button"); b.type = "button"; b.className = "ucai-quick"; b.textContent = text; b.addEventListener("click", function () { var input = document.querySelector("textarea"); if (!input) return; input.value = text; input.dispatchEvent(new Event("input", { bubbles:true })); input.focus(); }); box.appendChild(b); });
    composer.parentNode.insertBefore(box, composer);
  }

  var nativeFetch = window.fetch;
  window.fetch = function () {
    var args = arguments, u = String(args[0] && args[0].url ? args[0].url : args[0] || ""), o = args[1] || {};
    try { if (u.indexOf("/v1/chat") !== -1 && o.body) { var b = JSON.parse(o.body); if (b.message) language = lang(b.message); } } catch (_) {}
    return nativeFetch.apply(this, args).then(function (r) {
      if (u.indexOf("/v1/chat") !== -1 || u.indexOf("/v1/images/") !== -1) r.clone().json().then(function (d) { if (d) { if (Array.isArray(d.products)) products = d.products; type = String(d.type || ""); setTimeout(patch, 0); } }).catch(function () {});
      return r;
    });
  };
  new MutationObserver(patch).observe(document.body, { childList:true, subtree:true });
  patch();
})();
