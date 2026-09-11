/* Commerce UX layer for the existing Universal Commerce AI widget. */
(function () {
  "use strict";
  var script = document.currentScript || document.scripts[document.scripts.length - 1];
  var api = ((script && script.getAttribute("data-api-base")) || location.origin).replace(/\/$/, "");
  var products = [], language = "en", responseType = "", lastMessage = "";
  function lang(text) { return /[\u0980-\u09FF]/.test(String(text || "")) ? "bn" : "en"; }
  function url(value, base) { if (typeof value !== "string" || !value.trim()) return ""; try { var u = new URL(value.trim(), base || location.href); return /^https?:$/.test(u.protocol) ? u.href : ""; } catch (_) { return ""; } }
  function label(key) { return String(key || "").replace(/[_-]+/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }
  function attrs(p) { var out = [], src = p && (p.attributes || p.dynamic_attributes || p.metadata); if (src && typeof src === "object" && !Array.isArray(src)) Object.keys(src).forEach(function (k) { var v = src[k]; if (v !== null && v !== undefined && v !== "" && typeof v !== "object") out.push([label(k), String(v)]); }); var skip = {id:1,name:1,title:1,price:1,currency:1,currency_code:1,currency_symbol:1,stock:1,rating:1,review_count:1,product_url:1,url:1,link:1,image_url:1,image:1,main_image:1,thumbnail:1,attributes:1,dynamic_attributes:1,metadata:1,description:1}; Object.keys(p || {}).forEach(function (k) { var v = p[k]; if (skip[k] || out.length >= 5 || v === null || v === undefined || v === "" || typeof v === "object") return; if (/string|number|boolean/.test(typeof v)) out.push([label(k), String(v)]); }); var seen = {}; return out.filter(function (x) { var k=x[0]+"="+x[1]; if(seen[k]) return false; seen[k]=1; return true; }).slice(0,3); }
  function productFor(card) { var n = card.querySelector(".product-name"), name = n ? String(n.textContent || "").trim() : ""; var a = card.querySelector("a.action.primary[href]"), href = a ? a.href : ""; return products.find(function (p) { return (name && String(p.name || p.title || "").trim() === name) || (href && url(p.product_url || p.url || p.link) === href); }); }
  function buildChoices() {
    var text = String(lastMessage || "").toLowerCase();
    var type = String(responseType || "").toLowerCase();
    var bn = language === "bn";
    var delivery = /delivery|shipping|ship|ডেলিভারি|শিপিং|কুরিয়ার|কুরিয়ার|পৌঁছ|পাঠাব/.test(text);
    var returnPolicy = /return|refund|exchange|রিটার্ন|রিফান্ড|এক্সচেঞ্জ|বদল/.test(text);
    var warranty = /warranty|guarantee|ওয়ারেন্টি|ওয়ারেন্টি|গ্যারান্টি/.test(text);
    var price = /price|cost|cheap|cheaper|discount|offer|দাম|মূল্য|কম দাম|সস্তা|ডিসকাউন্ট|অফার/.test(text);
    var compare = /compare|comparison|তুলনা|দুটো|দুইটা|কোনটা ভালো|which is better/.test(text);
    var details = /detail|details|spec|specification|feature|বিস্তারিত|স্পেসিফিকেশন|ফিচার/.test(text);
    var link = /link|url|website|page|লিংক|ইউআরএল|ওয়েবসাইট|ওয়েবসাইট|পেজ/.test(text) || /link|url/.test(type);
    if (delivery) return bn ? ["Delivery info", "Talk to merchant"] : ["Delivery info", "Talk to merchant"];
    if (returnPolicy) return bn ? ["Return policy", "Talk to merchant"] : ["Return policy", "Talk to merchant"];
    if (warranty) return bn ? ["Warranty info", "Talk to merchant"] : ["Warranty info", "Talk to merchant"];
    if (compare) return bn ? ["বিস্তারিত", "আরও দেখুন"] : ["Tell me more", "Show more"];
    if (link) return bn ? ["পণ্য খুলুন", "আরও দেখুন"] : ["Shop now", "Show more"];
    if (details) return bn ? ["বিস্তারিত", "ছবি দেখুন", "আরও দেখুন"] : ["Tell me more", "View images", "Show more"];
    if (price) return bn ? ["কম দামে", "অফার দেখুন", "আরও দেখুন"] : ["Cheaper options", "See offers", "Show more"];
    if (products.length) return bn ? ["আরও দেখুন", "কম দামে", "স্টকে আছে"] : ["Show more", "Cheaper options", "In stock only"];
    return bn ? ["পণ্য খুঁজুন", "দাম জানুন"] : ["Find products", "Ask about price"];
  }
  function addQuickReplies(root) {
    if (!root) return;
    var existing = root.querySelector(".ucai-quick-replies");
    var choices = buildChoices().slice(0, 3);
    if (!choices.length) { if (existing) existing.remove(); return; }
    if (!existing) { existing = document.createElement("div"); existing.className="ucai-quick-replies"; var composer=root.querySelector(".composer"); if(composer)composer.parentNode.insertBefore(existing,composer); }
    existing.innerHTML = "";
    choices.forEach(function(text){var b=document.createElement("button");b.type="button";b.className="ucai-quick";b.textContent=text;b.addEventListener("click",function(){var input=root.querySelector("textarea"),send=root.querySelector(".composer button");if(!input)return;input.value=text;input.dispatchEvent(new Event("input",{bubbles:true}));input.focus();if(send)send.click();});existing.appendChild(b);});
  }
  function patch(root) {
    if (!root) return;
    if (!root.querySelector("#ucai-ux-style")) { var s=document.createElement("style"); s.id="ucai-ux-style"; s.textContent=".ucai-link{display:block;color:inherit;text-decoration:none}.ucai-link:focus-visible{outline:3px solid #93c5fd;outline-offset:2px}.ucai-attrs{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.ucai-attr{font-size:10px;padding:4px 7px;border:1px solid #e5e7eb;border-radius:999px;background:#f8fafc;color:#475569}.ucai-attr b{color:#334155}.ucai-quick-replies{display:flex;gap:6px;overflow-x:auto;padding:7px 10px;background:#fff;border-top:1px solid #f1f5f9;scrollbar-width:none}.ucai-quick-replies::-webkit-scrollbar{display:none}.ucai-quick{white-space:nowrap;border:1px solid #d8dde5;background:#fff;border-radius:999px;padding:6px 9px;font-size:11px;color:#475569;cursor:pointer}.ucai-quick:hover{border-color:#94a3b8;background:#f8fafc}"; root.appendChild(s); }
    root.querySelectorAll(".product").forEach(function(card){ if(card.dataset.ucaiUx)return; var p=productFor(card);if(!p)return;card.dataset.ucaiUx="1";var href=url(p.product_url||p.url||p.link,p.product_url||p.url||location.href);[card.querySelector(".product-image,.product-image-fallback"),card.querySelector(".product-option")].forEach(function(el){if(!el||!href||el.closest("a.ucai-link"))return;var a=document.createElement("a");a.className="ucai-link";a.href=href;a.target="_blank";a.rel="noopener noreferrer";el.parentNode.insertBefore(a,el);a.appendChild(el);});var img=card.querySelector("img.product-image");if(img){img.loading="lazy";img.decoding="async";img.addEventListener("error",function(){if(img.dataset.ucaiFallback)return;img.dataset.ucaiFallback="1";var f=document.createElement("div");f.className="product-image-fallback";f.textContent=language==="bn"?"ছবি পাওয়া যাচ্ছে না":"Image unavailable";img.replaceWith(f);});}var primary=card.querySelector("a.action.primary");if(primary&&href)primary.textContent=/link|url/.test(responseType.toLowerCase())?(language==="bn"?"পণ্য খুলুন":"Shop now"):(language==="bn"?"পণ্য দেখুন":"View product");var pairs=attrs(p),body=card.querySelector(".product-body")||card;if(pairs.length&&!card.querySelector(".ucai-attrs")){var box=document.createElement("div");box.className="ucai-attrs";pairs.forEach(function(x){var c=document.createElement("span");c.className="ucai-attr";var b=document.createElement("b");b.textContent=x[0]+": ";c.appendChild(b);c.appendChild(document.createTextNode(x[1]));box.appendChild(c);});var meta=body.querySelector(".product-meta");if(meta&&meta.nextSibling)body.insertBefore(box,meta.nextSibling);else body.appendChild(box);}});
    addQuickReplies(root);
  }
  function injectPremiumCss(root){ if(!root||root.querySelector("#ucai-premium-css"))return; var link=document.createElement("link"); link.id="ucai-premium-css"; link.rel="stylesheet"; link.href=api+"/premium-overrides.css"; root.appendChild(link); }
  function observe(){var tries=0;(function find(){var host=Array.prototype.find.call(document.body.children,function(x){return x.shadowRoot&&x.shadowRoot.querySelector(".panel")});if(!host){if(++tries<100)setTimeout(find,50);return;}var root=host.shadowRoot;injectPremiumCss(root);new MutationObserver(function(){patch(root)}).observe(root,{childList:true,subtree:true});patch(root);})();}
  var nativeFetch=window.fetch;window.fetch=function(){var args=arguments,u=String(args[0]&&args[0].url?args[0].url:args[0]||""),o=args[1]||{};try{if(u.indexOf("/v1/chat")!==-1&&o.body){var b=JSON.parse(o.body);if(b.message){lastMessage=String(b.message);language=lang(b.message);}}}catch(_){}return nativeFetch.apply(this,args).then(function(r){if(u.indexOf("/v1/chat")!==-1||u.indexOf("/v1/images/")!==-1){r.clone().json().then(function(d){if(d){if(Array.isArray(d.products))products=d.products;responseType=String(d.type||d.intent||"");setTimeout(function(){var hs=document.body.children;for(var i=0;i<hs.length;i++)if(hs[i].shadowRoot)patch(hs[i].shadowRoot);},0);}}).catch(function(){});}return r;});};
  var core=document.createElement("script");core.src=api+"/widget-core.js";core.async=true;core.setAttribute("data-key",script&&script.getAttribute("data-key")||"");core.setAttribute("data-api-base",api);["data-color","data-greeting","data-position"].forEach(function(a){if(script&&script.hasAttribute(a))core.setAttribute(a,script.getAttribute(a));});core.onload=observe;document.head.appendChild(core);
})();
