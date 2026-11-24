/* ON + optional site access enable automatic URL checks. Screenshots stay per-click. */
importScripts("scan-core.js", "page-warning.js");
const API = "http://127.0.0.1:8000";
const MAX_IMAGE_BASE64 = 6700000;
const AUTO_ORIGINS = ["http://*/*", "https://*/*"];
const WARNING_COOLDOWN_MS = 5 * 60 * 1000;
const entries = new Map(), pending = new Map(), controllers = new Set(), warningTimes = new Map();
let active = 0, generation = 0;
async function settings() {
  return { ...await chrome.storage.local.get(["enabled", "imageEnabled", "notificationsEnabled"]),
    ...await chrome.storage.session.get("apiKey") };
}
async function request(path, apiKey, payload, signal) {
  const controller = new AbortController(), abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  controllers.add(controller);
  const timeout = setTimeout(abort, 15000);
  try {
    const response = await fetch(API + path, {
      method: payload === undefined ? "GET" : "POST", cache: "no-store", credentials: "omit", redirect: "error",
      signal: controller.signal, headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: payload === undefined ? undefined : JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Local API unavailable (${response.status}).`);
    return await response.json();
  } finally { clearTimeout(timeout); controllers.delete(controller); signal?.removeEventListener("abort", abort); }
}
async function badge(tabId, text, color = "#64746b") {
  try {
    await chrome.action.setBadgeBackgroundColor({ tabId, color });
    await chrome.action.setBadgeText({ tabId, text });
  } catch (_) { /* Tab may have closed. */ }
  if (typeof publishBridgeSoon === "function") publishBridgeSoon();
}
async function clearWarning(tabId) {
  try { await chrome.tabs.sendMessage(tabId, { type: "PHISHGUARD_CLEAR_WARNING" }); }
  catch (_) { /* A page may not contain our warning listener. */ }
  try { await chrome.scripting.executeScript({ target: { tabId }, func: removePhishGuardWarning }); }
  catch (_) { /* Restricted pages cannot receive an injected warning. */ }
}
function cancel(tabId, removeEntry = false) {
  const old = entries.get(tabId);
  if (old) { clearTimeout(old.timer); old.controller?.abort(); }
  pending.delete(tabId);
  if (removeEntry) entries.delete(tabId);
}
async function stopAll() {
  generation += 1;
  const ids = [...entries.keys()];
  for (const id of ids) cancel(id, true);
  pending.clear(); warningTimes.clear();
  for (const controller of controllers) controller.abort();
  // A service-worker restart loses memory, but an already injected warning may remain.
  try { for (const tab of await chrome.tabs.query({})) if (!ids.includes(tab.id)) ids.push(tab.id); }
  catch (_) { /* Browser may be shutting down. */ }
  await Promise.allSettled(ids.map(async id => { await badge(id, ""); await clearWarning(id); }));
  try {
    const notices = await chrome.notifications.getAll();
    await Promise.allSettled(Object.keys(notices).filter(id => id.startsWith("pg-")).map(id => chrome.notifications.clear(id)));
  } catch (_) { /* OS notifications are optional. */ }
}
function schedule(tab, invalidate = false) {
  if (!tab || tab.id === undefined || tab.incognito || tab.status === "loading" || !PhishGuardCore.url(tab.url)) return;
  const parsed = new URL(tab.url), backend = new URL(API);
  if (parsed.origin === backend.origin || (backend.hostname === "127.0.0.1" && parsed.origin === backend.protocol + "//localhost:" + backend.port)) return;
  const old = entries.get(tab.id);
  if (!invalidate && old?.url === tab.url && (old.state === "checking" || old.timer || Date.now() - (old.completed || 0) < 30000)) return;
  cancel(tab.id);
  const entry = { url: tab.url, state: "queued", generation, scanId: crypto.randomUUID() };
  entries.set(tab.id, entry);
  void badge(tab.id, "");
  if (invalidate) void clearWarning(tab.id);
  entry.timer = setTimeout(() => {
    entry.timer = null; pending.set(tab.id, entry); drain();
  }, 600);
}
function drain() {
  while (active < 3 && pending.size) {
    const [id, entry] = pending.entries().next().value;
    pending.delete(id); active += 1;
    scanTab(id, entry).catch(() => {}).finally(() => { active -= 1; drain(); });
  }
}
async function current(tabId, entry) {
  if (entries.get(tabId) !== entry || entry.generation !== generation) return false;
  const state = await settings();
  if (!state.enabled || !state.apiKey) return false;
  try {
    const tab = await chrome.tabs.get(tabId);
    return tab.url === entry.url && entries.get(tabId) === entry && entry.generation === generation;
  } catch (_) { return false; }
}
async function scanTab(tabId, entry) {
  if (!await current(tabId, entry)) return;
  const state = await settings(), url = PhishGuardCore.url(entry.url);
  if (!url || !await chrome.permissions.contains({ origins: [url.origin + "/*"] })) return;
  entry.controller = new AbortController(); entry.state = "checking";
  const started = performance.now();
  await badge(tabId, "…");
  try {
    // Origin only: never automatically send paths, query tokens, fragments, titles or pixels.
    const result = PhishGuardCore.result(await request("/api/v1/predict/url", state.apiKey, { url: url.origin + "/" }, entry.controller.signal));
    if (!await current(tabId, entry)) return;
    entry.result = result; entry.state = "complete"; entry.completed = Date.now();
    entry.latencyMs = performance.now() - started;
    await badge(tabId, result.verdict === "phishing" ? "!" : "", "#b42318");
    if (result.verdict !== "phishing") { await clearWarning(tabId); return; }
    const signature = tabId + ":" + url.origin;
    if (Date.now() - (warningTimes.get(signature) || 0) < WARNING_COOLDOWN_MS) return;
    warningTimes.set(signature, Date.now());
    if (warningTimes.size > 300) warningTimes.delete(warningTimes.keys().next().value);
    const content = PhishGuardCore.warning(url.hostname, result);
    if (!await current(tabId, entry)) return;
    try { await chrome.scripting.executeScript({ target: { tabId }, func: showPhishGuardWarning, args: [entry.url, content] }); }
    catch (_) { /* Restricted pages keep the toolbar alert. */ }
    if (!await current(tabId, entry)) { await clearWarning(tabId); return; }
    if (state.notificationsEnabled && await current(tabId, entry) && await chrome.permissions.contains({ permissions: ["notifications"] })) {
      try { await chrome.notifications.create("pg-" + tabId, {
        type: "basic", iconUrl: "icon128.png", title: content.title, message: content.host + "\n" + content.advice, priority: 1
      }); } catch (_) { /* OS notifications may be disabled. */ }
    }
  } catch (_) {
    if (await current(tabId, entry)) {
      entry.state = "unavailable"; entry.completed = Date.now(); entry.result = null;
      await badge(tabId, "?");
    }
  } finally { entry.controller = null; }
}
async function scanAll() {
  const state = await settings();
  if (!state.enabled || !state.apiKey || state.apiKey.length < 32) return;
  for (const tab of await chrome.tabs.query({})) schedule(tab);
}
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
  await chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
  await chrome.storage.local.set({ enabled: false, imageEnabled: false, notificationsEnabled: false });
  await chrome.alarms.create("phishguard-active-recheck", { periodInMinutes: 1 });
});
chrome.runtime.onStartup.addListener(async () => {
  const state = await settings();
  if (!state.apiKey) await chrome.storage.local.set({ enabled: false });
  await chrome.alarms.create("phishguard-active-recheck", { periodInMinutes: 1 });
  await scanAll();
});
chrome.alarms.onAlarm.addListener(async alarm => {
  if (typeof publishBridge === "function") void publishBridge();
  if (alarm.name === "phishguard-resume") {
    const state = await settings(), local = await chrome.storage.local.get("pauseUntil");
    if (local.pauseUntil && local.pauseUntil <= Date.now() && state.apiKey && await chrome.permissions.contains({ origins: AUTO_ORIGINS })) {
      await chrome.storage.local.set({ enabled: true, pauseUntil: 0 }); await scanAll();
    }
    return;
  }
  if (alarm.name !== "phishguard-active-recheck") return;
  const state = await settings();
  if (state.enabled && state.apiKey) for (const tab of await chrome.tabs.query({ active: true })) schedule(tab);
});
chrome.tabs.onUpdated.addListener((id, change, tab) => {
  if (change.url || change.status === "loading") { cancel(id, true); void badge(id, ""); void clearWarning(id); }
  if (change.url || change.status === "complete") settings().then(state => {
    if (state.enabled && state.apiKey) schedule(tab, Boolean(change.url));
  }).catch(() => {});
});
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try { const state = await settings(); if (state.enabled && state.apiKey) schedule(await chrome.tabs.get(tabId)); }
  catch (_) { /* Tab closed or session not ready. */ }
});
chrome.tabs.onRemoved.addListener(id => { cancel(id, true); });
chrome.storage.onChanged.addListener((changes, area) => {
  if ((area === "local" && changes.enabled) || (area === "session" && changes.apiKey)) stopAll().then(scanAll).catch(() => {});
});
chrome.permissions.onRemoved.addListener(async () => {
  await stopAll();
  if (!await chrome.permissions.contains({ origins: AUTO_ORIGINS })) await chrome.storage.local.set({ enabled: false });
  else await scanAll();
});
async function notificationClicked(id) {
  if (!id.startsWith("pg-")) return;
  const tabId = Number(id.slice(3));
  try {
    const tab = await chrome.tabs.get(tabId), entry = entries.get(tabId);
    if (!entry || entry.result?.verdict !== "phishing" || !await current(tabId, entry)) return;
    await chrome.windows.update(tab.windowId, { focused: true }); await chrome.tabs.update(tabId, { active: true });
    await chrome.scripting.executeScript({ target: { tabId }, func: showPhishGuardWarning,
      args: [entry.url, PhishGuardCore.warning(new URL(entry.url).hostname, entry.result)] });
  } catch (_) { /* Ignore stale notifications. */ }
}
let notificationListenerRegistered = false;
function registerNotifications() {
  if (!notificationListenerRegistered && chrome.notifications?.onClicked) {
    chrome.notifications.onClicked.addListener(notificationClicked);
    notificationListenerRegistered = true;
  }
}
registerNotifications();
chrome.permissions.onAdded?.addListener(registerNotifications);
async function manual(message) {
  const ticket = generation;
  const state = await settings();
  if (!state.enabled || !state.apiKey || state.apiKey.length < 32) throw new Error("Turn ON and save a session key first.");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = PhishGuardCore.url(tab?.url);
  if (!url) throw new Error("This page cannot be checked.");
  if (message.type === "SCAN") return PhishGuardCore.result(await request("/api/v1/predict/url", state.apiKey, { url: url.origin + "/" }));
  if (!state.imageEnabled || message.consent !== true) throw new Error("Screenshot consent is required.");
  if ((await request("/health", state.apiKey)).vision_enabled !== true) throw new Error("Screenshot model unavailable.");
  async function captureStillAuthorized() {
    const now = await settings();
    const [visible] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (generation !== ticket || !now.enabled || !now.imageEnabled || now.apiKey !== state.apiKey ||
        visible?.id !== tab.id || visible?.url !== tab.url) throw new Error("Page or consent settings changed; capture again explicitly.");
  }
  await captureStillAuthorized();
  const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 45 });
  await captureStillAuthorized();
  const data = image.startsWith("data:image/jpeg;base64,") ? image.slice(image.indexOf(",") + 1) : "";
  if (!data || data.length > MAX_IMAGE_BASE64) throw new Error("Screenshot exceeds the upload limit.");
  return PhishGuardCore.result(await request("/api/v1/predict/image", state.apiKey, { consent: true, image_base64: data }));
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || ![chrome.runtime.getURL("popup.html"), chrome.runtime.getURL("connect.html")].includes(sender.url)) return false;
  const operation = async () => {
    if (message.type === "SET_ENABLED") {
      if (message.enabled) {
        const state = await settings();
        if (!state.apiKey || state.apiKey.length < 32) throw new Error("Save your local session API key first.");
        if (!await chrome.permissions.contains({ origins: AUTO_ORIGINS })) throw new Error("Allow website access to enable automatic checks.");
      }
      await chrome.storage.local.set({ enabled: message.enabled === true });
      await chrome.storage.local.set({ pauseUntil: 0 });
      await chrome.alarms.clear("phishguard-resume");
      if (message.enabled) await chrome.alarms.create("phishguard-active-recheck", { periodInMinutes: 1 });
      if (!message.enabled) await stopAll();
      return { enabled: message.enabled === true };
    }
    if (message.type === "GET_STATUS") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }), entry = entries.get(tab?.id);
      return { state: entry?.state || "not_checked", result: entry?.result || null,
        checkedAt: entry?.completed || null, hostname: PhishGuardCore.url(tab?.url)?.hostname || null };
    }
    if (["SCAN", "SCAN_IMAGE"].includes(message.type)) return manual(message);
    throw new Error("Unsupported request.");
  };
  operation().then(result => respond({ ok: true, result })).catch(error => respond({ ok: false, error: error.message }));
  return true;
});
importScripts("dashboard-bridge.js");
