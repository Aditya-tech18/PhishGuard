const get = id => document.getElementById(id);
let busy = false;
function refresh() {
  get("state").textContent = get("enabled").checked ? "ON · automatic domain checks" : "OFF · no automatic checks";
  get("scan").disabled = busy || !get("enabled").checked;
  get("scanImage").disabled = busy || !get("enabled").checked || !get("imageEnabled").checked || !get("imageConsent").checked;
}
function describe(result, image = false) {
  const title = result.verdict === "phishing" ? "Yeh website scam ho sakti hai." : "Model ko high-risk signal nahi mila. Safety guarantee nahi hai.";
  return `${image ? "Visual check" : "Domain check"}: ${title} Model score ${(result.probability * 100).toFixed(1)}%.` +
    (result.reasons?.length ? "\n" + result.reasons.join("\n") : "");
}
async function message(payload) {
  const response = await chrome.runtime.sendMessage(payload);
  if (!response?.ok) throw new Error(response?.error || "Local server se connection nahi mila.");
  return response.result;
}
chrome.storage.local.get(["enabled", "imageEnabled", "notificationsEnabled"]).then(state => {
  for (const id of ["enabled", "imageEnabled", "notificationsEnabled"]) get(id).checked = state[id] === true;
  refresh();
});
get("enabled").addEventListener("change", async () => {
  const turnOn = get("enabled").checked;
  get("imageConsent").checked = false;
  try {
    // Must be requested directly from the user's click, before other asynchronous work.
    if (turnOn && !await chrome.permissions.request({ origins: ["http://*/*", "https://*/*"] })) throw new Error("Website permission nahi mili. Automatic checks OFF hain.");
    await message({ type: "SET_ENABLED", enabled: turnOn });
    get("result").textContent = turnOn ? "Open tabs check ho rahe hain. Warning sirf suspicious result par aayegi." : "Checks paused. Website warnings removed.";
  } catch (error) {
    get("enabled").checked = false;
    await chrome.storage.local.set({ enabled: false });
    get("result").textContent = error.message;
  }
  refresh();
});
get("notificationsEnabled").addEventListener("change", async () => {
  let enabled = get("notificationsEnabled").checked;
  if (enabled) enabled = await chrome.permissions.request({ permissions: ["notifications"] });
  get("notificationsEnabled").checked = enabled;
  await chrome.storage.local.set({ notificationsEnabled: enabled });
});
get("imageEnabled").addEventListener("change", async () => {
  await chrome.storage.local.set({ imageEnabled: get("imageEnabled").checked });
  get("imageConsent").checked = false; refresh();
});
get("imageConsent").addEventListener("change", refresh);
get("save").addEventListener("click", async () => {
  const key = get("key").value.trim();
  if (key.length < 32) { get("result").textContent = "Session key must contain at least 32 characters."; return; }
  await chrome.storage.session.set({ apiKey: key }); get("key").value = "";
  get("imageConsent").checked = false; refresh();
  get("result").textContent = "Session key saved. Ab automatic checks ON kar sakte ho.";
});
get("clear").addEventListener("click", async () => {
  await message({ type: "SET_ENABLED", enabled: false });
  await chrome.storage.session.remove("apiKey"); get("key").value = "";
  get("enabled").checked = false; get("result").textContent = "Key removed. Checks OFF."; refresh();
});
async function submit(type) {
  if (busy || !get("enabled").checked) return;
  if (type === "SCAN_IMAGE" && (!get("imageEnabled").checked || !get("imageConsent").checked)) return;
  busy = true; refresh(); get("result").textContent = "Checking…";
  try { get("result").textContent = describe(await message({ type, consent: type === "SCAN_IMAGE" }), type === "SCAN_IMAGE"); }
  catch (error) { get("result").textContent = error.message; }
  finally { busy = false; get("imageConsent").checked = false; refresh(); }
}
get("scan").addEventListener("click", () => submit("SCAN"));
get("scanImage").addEventListener("click", () => submit("SCAN_IMAGE"));
async function status() {
  if (busy || !get("enabled").checked) return;
  try {
    const value = await message({ type: "GET_STATUS" });
    get("site").textContent = value.hostname || "This page cannot be checked";
    get("live").textContent = value.state === "complete" ? describe(value.result) : value.state === "unavailable" ?
      "Check unavailable — local API/key verify karein. Is page ko safe nahi maana gaya." : "Waiting / checking…";
  } catch (_) { get("live").textContent = "Connection unavailable"; }
}
void status(); setInterval(status, 1200);
