/* Isolated-world functions. Untrusted strings are never interpreted as HTML. */
function removePhishGuardWarning() {
  if (globalThis.__phishGuardWarning?.listener) chrome.runtime.onMessage.removeListener(globalThis.__phishGuardWarning.listener);
  globalThis.__phishGuardWarning?.host?.remove();
  delete globalThis.__phishGuardWarning;
}
function showPhishGuardWarning(expectedURL, content) {
  if (location.href !== expectedURL || globalThis.__phishGuardWarning?.host?.isConnected) return false;
  if (globalThis.__phishGuardWarning?.listener) chrome.runtime.onMessage.removeListener(globalThis.__phishGuardWarning.listener);
  const host = document.createElement("div");
  host.setAttribute("data-phishguard-warning", "true");
  host.style.cssText = "all:initial;position:fixed;top:18px;right:18px;width:min(390px,calc(100vw - 36px));z-index:2147483647;color-scheme:light;";
  const root = host.attachShadow({ mode: "closed" }), style = document.createElement("style");
  style.textContent = `:host{font:14px/1.5 system-ui,sans-serif}*{box-sizing:border-box}
    .panel{font:14px/1.5 system-ui,sans-serif;max-height:70vh;overflow:auto;background:#fff;color:#14221a;border:1px solid #edc3ba;border-top:5px solid #b42318;border-radius:18px;box-shadow:0 14px 55px #14221a35;padding:20px}
    .brand{font-size:12px;font-weight:800;letter-spacing:.08em;color:#156535}h2{font-size:21px;line-height:1.2;margin:10px 0}
    .domain{font-family:ui-monospace,monospace;overflow-wrap:anywhere;font-weight:700}p{margin:10px 0}.note{font-size:11px;color:#59675f}
    .row{display:flex;gap:8px}button{font:inherit;cursor:pointer;border-radius:9px;padding:9px 12px;border:1px solid #d6e5da;background:#fff;color:#14221a}
    .primary{background:#fff500;border-color:#e0d800;font-weight:700}button:focus-visible{outline:3px solid #156535;outline-offset:2px}
    ul{padding-left:20px;font-size:13px}[hidden]{display:none!important}`;
  root.append(style);
  const panel = document.createElement("section"); panel.className = "panel";
  panel.setAttribute("role", "alert"); panel.setAttribute("aria-label", "PhishGuard website warning");
  const text = (tag, value, className) => {
    const el = document.createElement(tag); el.textContent = value;
    if (className) el.className = className;
    panel.append(el); return el;
  };
  text("div", "PHISHGUARD · WEBSITE WARNING", "brand");
  text("h2", content.title); text("div", content.host, "domain"); text("p", content.advice);
  const details = document.createElement("div"); details.hidden = true;
  const list = document.createElement("ul");
  for (const reason of content.reasons) { const li = document.createElement("li"); li.textContent = reason; list.append(li); }
  details.append(list); panel.append(details);
  const row = document.createElement("div"); row.className = "row";
  const why = document.createElement("button"); why.className = "primary"; why.textContent = "Kyun warning aayi?";
  why.setAttribute("aria-expanded", "false");
  why.addEventListener("click", () => { details.hidden = !details.hidden; why.setAttribute("aria-expanded", String(!details.hidden)); });
  const close = document.createElement("button"); close.textContent = "Dismiss"; close.addEventListener("click", () => host.remove());
  row.append(why, close); panel.append(row); text("p", content.note, "note"); root.append(panel);
  (document.documentElement || document.body).append(host);
  const listener = (message, sender) => {
    if (sender.id === chrome.runtime.id && message?.type === "PHISHGUARD_CLEAR_WARNING") {
      host.remove(); chrome.runtime.onMessage.removeListener(listener); delete globalThis.__phishGuardWarning;
    }
  };
  chrome.runtime.onMessage.addListener(listener);
  globalThis.__phishGuardWarning = { host, root, listener }; return true;
}
