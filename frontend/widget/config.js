/*!
 * Reference config for embedding the Universal Commerce AI widget
 * (app/static/widget.js, served at /widget.js).
 *
 * Most merchants just paste the <script> snippet the admin
 * dashboard (/admin) generates for them. This file is for the
 * minority of integrations that build the embed tag programmatically
 * — a CMS plugin, a tag-manager template, a framework component —
 * instead of hand-writing HTML.
 *
 * Not loaded by the widget itself; import/copy what you need.
 */

/**
 * @typedef {Object} WidgetConfig
 * @property {string} apiKey     Required. The store's public key (pk_live_...).
 * @property {string} [apiBase]  Override API origin. Defaults to the
 *                                script's own origin — only set this
 *                                if the widget script is hosted on a
 *                                different domain than the API.
 * @property {string} [color]    Accent color, any valid CSS color.
 * @property {string} [greeting] First assistant bubble shown on open.
 * @property {"bottom-right"|"bottom-left"} [position]
 */

/** Default values matching app/static/widget.js's own fallbacks. */
export const WIDGET_DEFAULTS = {
  color: "#111827",
  position: "bottom-right",
};

/**
 * Builds and inserts the widget <script> tag from a config object —
 * the programmatic equivalent of pasting the snippet from /admin.
 *
 * @param {WidgetConfig} config
 * @param {string} [widgetSrc] Defaults to "/widget.js" (same origin).
 * @returns {HTMLScriptElement}
 */
export function mountWidget(config, widgetSrc) {
  if (!config || !config.apiKey) {
    throw new Error("mountWidget: config.apiKey is required (pk_live_...)");
  }

  const script = document.createElement("script");
  script.src = widgetSrc || "/widget.js";
  script.async = true;
  script.setAttribute("data-key", config.apiKey);

  if (config.apiBase) script.setAttribute("data-api-base", config.apiBase);
  if (config.color) script.setAttribute("data-color", config.color);
  if (config.greeting) script.setAttribute("data-greeting", config.greeting);
  if (config.position) script.setAttribute("data-position", config.position);

  document.body.appendChild(script);
  return script;
}

/**
 * Renders the plain-HTML embed snippet as a string, e.g. for a CMS
 * "paste this in your theme" field.
 *
 * @param {WidgetConfig} config
 * @param {string} [host] API/script host, e.g. "https://app.example.com".
 *                         Required for cross-domain embeds (a merchant's
 *                         storefront embedding a widget served by your
 *                         platform).
 * @returns {string}
 */
export function embedSnippet(config, host) {
  if (!config || !config.apiKey) {
    throw new Error("embedSnippet: config.apiKey is required (pk_live_...)");
  }

  const base = host ? host.replace(/\/$/, "") : "";
  const attrs = [`data-key="${config.apiKey}"`];

  if (config.apiBase) attrs.push(`data-api-base="${config.apiBase}"`);
  if (config.color) attrs.push(`data-color="${config.color}"`);
  if (config.greeting) attrs.push(`data-greeting="${config.greeting}"`);
  if (config.position) attrs.push(`data-position="${config.position}"`);

  return `<script src="${base}/widget.js" ${attrs.join(" ")} async></script>`;
}
