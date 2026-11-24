globalThis.PhishGuardCore = {
  url(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url : null;
    } catch (_) { return null; }
  },
  result(value) {
    if (!value || typeof value.probability !== "number" || !Number.isFinite(value.probability) || value.probability < 0 || value.probability > 1 || !["phishing", "low_risk"].includes(value.verdict)) throw new Error("Invalid model response; no safety verdict available.");
    return { probability: value.probability, verdict: value.verdict,
      model_version: String(value.model_version || "unknown").slice(0, 120),
      reasons: Array.isArray(value.reasons) ? value.reasons.filter(x => typeof x === "string").slice(0, 4).map(x => x.slice(0, 180)) : [],
      review_required: value.review_required === true,
      coverage_warning: typeof value.coverage_warning === "string" ? value.coverage_warning.slice(0, 250) : null };
  },
  warning(host, result) {
    const labels = {
      host_length: "Website address ki length ka pattern model ne flag kiya.",
      url_length: "Website address ke structure par model ko suspicious signal mila.",
      host_labels: "Domain/subdomain structure model ke decision ka hissa tha.",
      host_digit_ratio: "Domain mein digits ka pattern model ke decision ka hissa tha.",
      digit_ratio: "Address mein digits ka pattern model ke decision ka hissa tha.",
      hyphens: "Address mein hyphens ka pattern model ne flag kiya.",
      dots: "Domain ke dot/subdomain pattern par model ne signal diya.",
      entropy: "Address ke character-pattern feature ka model ke decision mein role tha.",
      host_entropy: "Domain ke character-pattern feature ka model ke decision mein role tha.",
      ip_host: "IP/domain hostname type model ke decision ka ek feature tha.",
      punycode: "Encoded domain-name indicator model ke decision ka ek feature tha.",
      suspicious_tokens: "Domain ke word-pattern feature ka model ke decision mein role tha.",
      port_nonstandard: "Website port ka pattern model ke decision ka hissa tha.",
      https: "Address ka protocol model ke decision ka hissa tha. HTTPS akela safety ka proof nahi hai.",
      repeated_chars: "Domain mein repeated characters model ke decision ka hissa the."
    };
    return { host: String(host).slice(0, 253), title: "Yeh website scam ho sakti hai",
      advice: "Password, OTP ya payment details dene se pehle website verify karein.",
      reasons: result.reasons.length ? result.reasons.map(reason => labels[reason] || reason) : ["URL model ne is domain ko suspicious flag kiya. Detailed reason available nahi hai."],
      note: "Model galat bhi ho sakta hai. Yeh confirmed scam ka proof nahi hai." };
  }
};
