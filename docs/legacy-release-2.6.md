# PhishGuard 2.6 — local browser protection

Three dashboard pages, an opt-in Chrome extension, local URL inference, separately consented screenshot CNN inference, and separately runnable Spark/Kafka pipelines.

## Run from VS Code

Open this project folder and run:

```bash
bash start_local.sh
```

First launch creates `.venv-phishguard26` and installs dependencies. It needs internet for package downloads; it preserves `.venv`, `.env`, datasets and old models. Python 3.11–3.13 is required; Python 3.11 is the tested version.

Open **http://127.0.0.1:8000**. Keep the terminal running. Ctrl+C stops the engine. Exactly three application pages: Home, Live Detection, Model & System. Fonts/styles/scripts are served locally.

## Enable the browser extension

1. Visit `chrome://extensions` in Chrome, enable Developer mode and choose **Load unpacked**.
2. Select this project's `extension` folder. Disable older PhishGuard copies to avoid duplicate warnings.
3. Open the dashboard in the same Chrome browser; click **Connect extension**.
4. In the extension setup page, enable automatic checks and approve website access. The browser requires this explicit permission gesture.
5. Return to the dashboard. The switch becomes active only after the extension acknowledges it. Existing accessible tabs and new navigation are checked; suspicious results show a friendly scam warning and reasons. Low-risk results show no popup.

Automatic checks send only HTTP(S) origins to the local engine. No URL paths, query strings, titles, cookies, credentials or automatic screenshots. Current tab state and events are memory-only and removed when protection is turned OFF. Aggregate counters remain until server restart. Per-capture screenshot checks and dashboard file uploads require explicit consent. Restricted browser pages and incognito tabs are skipped.

## Desktop installation / merge

```bash
python3 scripts/install_local_release.py --target "$HOME/Desktop/PhishGuard"
python3 scripts/install_local_release.py --target "$HOME/Desktop/PhishGuard" --apply
```

Preview comes first. Apply backs up replaced code to a sibling `PhishGuard.code-backup-<timestamp>` folder, journals changes and adds models/reports under `releases/2.6.0`. Existing raw data, model files, reports, `.env`, `.git` and `.venv` are preserved. `config/local-install.json` points the launcher at the new model artifacts. Existing extra files are retained. Backups can be restored with `scripts/rollback_merge.py`; versioned model additions are retained for review.

## Actual validation and limits

Read [BUILD_REPORT.md](BUILD_REPORT.md). URL precision 91.24%, recall 82.20% on its recorded held-out origin split. CNN precision 88.16%, recall 88.36% on a **previously observed test audit** after threshold-policy revision; this is not a fresh independent confirmation or a live guarantee. No new model training was performed for this UI release.

Warnings do not block navigation or form submission. Origin-only checks can miss compromised legitimate domains and misclassify domains. There is no guarantee that a warning arrives before a user interacts with a page. WHOIS, TLS/DNSSEC inspection, OCR/brand matching, ONNX, SHAP explanations and live distributed-cluster telemetry are not implemented by this dashboard. Kafka/Spark source is included and must be started separately; an idle local dashboard is not evidence those services are running.

The supplied frontend HTML was adapted to show real connection/results and avoid unsupported benchmark claims; it is not certified as a pixel-identical rendering of the reference images. Decorative browser/warning illustrations are explicitly sample content.

For the separate batch/streaming, training, legacy Streamlit, Vercel packaging, and operating instructions, see [docs/legacy-readme.md](docs/legacy-readme.md) and the other `docs` files. Vercel does not host the local CNN/Kafka/Spark process; this delivery is a local build, not a public deployment.
