/* The local, first-party dashboard can pair/control this extension; no wildcard senders. */
let bridgeTimer = null;
let bridgeBusy = false;
chrome.tabs.onRemoved.addListener(() => publishBridgeSoon());
function publishBridgeSoon() {
  if (!bridgeTimer) bridgeTimer = setTimeout(() => {
    bridgeTimer = null; void publishBridge();
  }, 900);
}
async function publishBridge() {
  if (bridgeBusy) return;
  bridgeBusy = true;
  try {
    const session = await chrome.storage.session.get(["apiKey", "dashboardPaired", "agentId"]);
    if (!session.dashboardPaired || !session.apiKey || !session.agentId) return;
    const local = await chrome.storage.local.get(["enabled", "pauseUntil"]);
    const permitted = await chrome.permissions.contains({ origins: AUTO_ORIGINS });
    const tabs = [];
    for (const [id, entry] of entries) {
      const url = PhishGuardCore.url(entry.url);
      if (!url) continue;
      const result = entry.result;
      tabs.push({ tab_id: id, origin: url.origin, state: entry.state,
        scan_id: entry.scanId || "", verdict: result?.verdict || null,
        probability: result?.probability ?? null, model_version: result?.model_version || "",
        reasons: result?.reasons || [], checked_at: entry.completed ? entry.completed / 1000 : null,
        latency_ms: entry.latencyMs ?? null });
    }
    await request("/api/v1/browser/report", session.apiKey, {
      extension_id: chrome.runtime.id, agent_id: session.agentId,
      enabled: local.enabled === true, paused_until: (local.pauseUntil || 0) / 1000,
      permission_granted: permitted, total_tabs: tabs.length, tabs: local.enabled ? tabs.slice(-200) : []
    });
  } catch (_) { /* A disconnected dashboard/API never disables local warning controls. */ }
  finally { bridgeBusy = false; }
}
function dashboardOriginAllowed(sender) {
  try {
    const actual = new URL(sender.url || sender.origin).origin;
    const expected = new URL(API);
    return actual === expected.origin ||
      (expected.hostname === "127.0.0.1" && actual === expected.protocol + "//localhost:" + expected.port);
  } catch (_) { return false; }
}
chrome.runtime.onMessageExternal.addListener((message, sender, respond) => {
  if (!dashboardOriginAllowed(sender)) return false;
  const work = async () => {
    if (message.type === "PG_PING") {
      const local = await chrome.storage.local.get(["enabled", "pauseUntil"]);
      return { installed: true, version: chrome.runtime.getManifest().version,
        enabled: local.enabled === true, pausedUntil: local.pauseUntil || 0 };
    }
    if (message.type === "PG_CONNECT") {
      if (typeof message.apiKey !== "string" || message.apiKey.length < 32 || message.apiKey.length > 256) throw new Error("Invalid local session key");
      // Confirm the key with the configured API before trusting/persisting it in session memory.
      const current = await request("/api/v1/browser/session", message.apiKey);
      const existing = await chrome.storage.session.get("agentId");
      if (current.extension_connected && current.extension_id === chrome.runtime.id) {
        await request("/api/v1/browser/disconnect", message.apiKey, {});
      }
      await chrome.storage.session.set({ apiKey: message.apiKey, dashboardPaired: true,
        agentId: existing.agentId || crypto.randomUUID() });
      await publishBridge();
      if (!await chrome.permissions.contains({ origins: AUTO_ORIGINS })) {
        await chrome.tabs.create({ url: chrome.runtime.getURL("connect.html") });
        return { paired: true, permissionRequired: true };
      }
      return { paired: true, permissionRequired: false };
    }
    const state = await settings();
    if (typeof message.apiKey !== "string" || message.apiKey !== state.apiKey) throw new Error("Connect the current local session first");
    if (message.type === "PG_CONTROL") {
      if (message.enabled && !await chrome.permissions.contains({ origins: AUTO_ORIGINS })) {
        await chrome.tabs.create({ url: chrome.runtime.getURL("connect.html") });
        return { permissionRequired: true, enabled: false };
      }
      await chrome.alarms.clear("phishguard-resume");
      await chrome.storage.local.set({ pauseUntil: 0, enabled: message.enabled === true });
      if (!message.enabled) await stopAll();
      else await scanAll();
      await publishBridge();
      return { enabled: message.enabled === true };
    }
    if (message.type === "PG_PAUSE") {
      const pauseUntil = Date.now() + 3600000;
      await chrome.storage.local.set({ enabled: false, pauseUntil });
      await stopAll();
      await chrome.alarms.create("phishguard-resume", { when: pauseUntil });
      await publishBridge(); return { pausedUntil: pauseUntil };
    }
    if (["PG_FOCUS_TAB", "PG_CLOSE_TAB", "PG_VISUAL"].includes(message.type)) {
      if (!Number.isInteger(message.tabId) || !entries.has(message.tabId)) throw new Error("This tab is not in the monitored session");
      const tab = await chrome.tabs.get(message.tabId);
      if (message.type === "PG_CLOSE_TAB") {
        await chrome.tabs.remove(tab.id); await publishBridge(); return { closed: true };
      }
      await chrome.windows.update(tab.windowId, { focused: true });
      await chrome.tabs.update(tab.id, { active: true });
      if (message.type === "PG_VISUAL") {
        try { await chrome.action.openPopup(); }
        catch (_) { return { focused: true, openToolbar: true }; }
      }
      return { focused: true };
    }
    throw new Error("Unsupported dashboard command");
  };
  work().then(result => respond({ ok: true, result }))
    .catch(error => respond({ ok: false, error: error.message }));
  return true;
});
