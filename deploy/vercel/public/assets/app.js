"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let key = "", busy = false;
  const refresh = () => { $("scan").disabled = busy || !key || !$("consent").checked; $("url").disabled = busy; $("clear").disabled = busy; $("consent").disabled = busy; };
  const message = value => { $("form-message").textContent = value; };
  function forget() { key = ""; $("api-key").value = ""; $("key-state").textContent = "Not set"; refresh(); }
  $("save-key").addEventListener("click", () => {
    const value = $("api-key").value.trim();
    if (value.length < 32) { message("Use the server key, with at least 32 characters."); return; }
    key = value; $("api-key").value = ""; $("key-state").textContent = "Set for this page"; $("access").open = false; message(""); refresh();
  });
  $("forget").addEventListener("click", () => { forget(); message("Access key forgotten."); });
  $("clear").addEventListener("click", () => { $("url").value = ""; $("consent").checked = false; $("prediction").hidden = true; $("empty").hidden = false; message(""); refresh(); $("url").focus(); });
  $("consent").addEventListener("change", refresh);
  $("url").addEventListener("input", () => { $("consent").checked = false; $("prediction").hidden = true; $("empty").hidden = false; message(""); refresh(); });
  window.addEventListener("pagehide", forget);
  $("scan-form").addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !key || !$("consent").checked) return;
    let url;
    try {
      const raw = $("url").value.trim();
      if (raw.length > 2048 || /[\s\\\x00-\x1f\x7f]/.test(raw)) throw new Error();
      url = new URL(raw);
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) throw new Error();
      url.search = ""; url.hash = "";
    } catch (_) { message("Enter a complete HTTP(S) URL without credentials, spaces or controls."); $("consent").checked = false; refresh(); return; }
    busy = true; refresh(); message("Checking the URL structure…");
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch("/api/v1/predict/url", {method:"POST", credentials:"omit", redirect:"error", cache:"no-store", signal:controller.signal, headers:{"Content-Type":"application/json", "X-API-Key":key}, body:JSON.stringify({url:url.href})});
      if (!response.ok) {
        const messages = {401:"The access key was rejected. Set the deployment key again.", 422:"That URL is unsupported. Use a public HTTP(S) hostname without credentials.", 429:"Too many requests. Wait a minute before checking again.", 413:"The request exceeds the supported size."};
        throw new Error(messages[response.status] || "The service could not complete this check. Try again later.");
      }
      const data = await response.json();
      if (!Number.isFinite(data.probability) || data.probability < 0 || data.probability > 1 || !["phishing", "low_risk"].includes(data.verdict)) throw new Error("The service returned an invalid result.");
      const suspicious = data.verdict === "phishing";
      $("verdict").textContent = data.review_required ? "Review needed · limited coverage" : suspicious ? "Suspicious domain pattern" : "Low model risk";
      $("verdict").classList.toggle("suspicious", suspicious);
      $("score").textContent = (data.probability * 100).toFixed(1) + "%";
      $("score-bar").style.width = (data.probability * 100).toFixed(1) + "%";
      $("score-bar").classList.toggle("suspicious", suspicious);
      $("advice").textContent = data.review_required ? data.coverage_warning : suspicious ? "Pause before opening. Verify the sender and navigate through the official website independently." : "This URL has fewer patterns the model associates with phishing. Verify the destination before sharing credentials.";
      $("model-version").textContent = data.model_version; $("inspected-url").textContent = url.href;
      $("prediction").hidden = false; $("empty").hidden = true; message("Check complete. Consent again for another scan.");
    } catch (error) { message(error.name === "AbortError" ? "The check timed out. Please try again." : error.message); }
    finally { clearTimeout(timer); busy = false; $("consent").checked = false; refresh(); }
  });
  fetch("/health", {credentials:"omit", cache:"no-store"}).then(response => {if (!response.ok) throw new Error(); return response.json();}).then(() => {$("connection").textContent = "URL service ready"; $("connection").classList.add("ready");}).catch(() => {$("connection").textContent = "Service unavailable";});
  fetch("/api/v1/model-card", {credentials:"omit", cache:"no-store"}).then(response => {if (!response.ok) throw new Error(); return response.json();}).then(card => {$("precision").textContent = (card.test.precision*100).toFixed(2)+"%"; $("recall").textContent = (card.test.recall*100).toFixed(2)+"%"; $("test-rows").textContent = card.test.rows.toLocaleString("en-US");}).catch(() => {});
  refresh();
})();
