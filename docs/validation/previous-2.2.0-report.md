# PhishGuard 2.2.0 — measured release status

A complete local source repository and a separate Vercel-ready URL web/API export. Existing Desktop project/data remain untouched; safe merge is preview-only unless explicitly applied. No presentation is included.

## What changed

The old full-URL model learned a serious dataset shortcut: training had 16,977 legitimate URLs and **zero legitimate non-root paths**, versus 11,202 phishing paths. Ordinary login/article probes exposed overflagging despite old 98% held-out metrics. Those historical metrics must not be presented as evidence of current-world accuracy.

The new selected **origin-only Gradient Boosting**, version `3a4516d9641014ee`, validates the full URL but ignores path/query in its numeric features. Curated origins with conflicting labels were entirely excluded. Five families were compared on validation; promotion requires validation F1 >=0.7 and FPR <=5%. No benign-domain allowlist or synthetic safe-path labels were added.

New held-out origin test: 8,125 rows, precision **91.24%**, recall **82.20%**, F1 **86.49%**, FPR **3.37%**. Train 27,401 and validation 8,482. These are different inputs/splits from the previous full-URL experiment. Some legitimate hosts still overflag. API, extension and web UI expose conservative review notices for path/login shapes; raw scores remain unchanged and are not verified threat decisions. Independent current-source/time evaluation is still required for protection claims.

The real-data CNN now uses layout-preserving spatial pooling and dropout. Validation F1 improved from **26.58% to 46.07%** at a validation false-positive constraint. Promoted using validation only. The 2,541-image test gave precision **52.50%**, recall **34.29%**, F1 **41.48%**, ROC AUC **0.8699**, FPR **3.31%**. This reuses a previously observed test split, not a new independent external benchmark. It misses many phishing screenshots and stays explicitly experimental. See image preparation, selection and matching weights reports.

## Executed checks

- **162 tests passed**, 9 warnings, 129.23 seconds, **77% statement coverage**. Real Spark, isolated Kafka, Torch and Chromium markers enabled.
- Actual Chrome toolbar with the final URL/CNN models: URL scan, per-capture screenshot consent/inference, ON/OFF and key-clear passed.
- Actual Vercel-export HTTP app with selected URL model in desktop/mobile Chromium: prediction, cleaned submission, consent reset, memory-only key, zero external requests, no console errors and no horizontal overflow passed.
- Managed local API/dashboard launcher with both final model artifacts: authenticated URL/image readiness passed, processes stopped and transient key removed.
- Ruff, JavaScript syntax and medium/high Bandit source scan passed. ZIP CRC, exact archived bytes and SHA-256 manifests checked by packagers.
- Final selected-artifact container check: **passed**. Historical 2.2 container tests did build and run API/vision/Kafka with earlier selected artifacts; final rebuild encountered isolated VM disk exhaustion and was retried after removing only obsolete task image/cache. Only a matching final report is marked passed.

## Vercel profile

The separate lean export includes static web UI, FastAPI, portable NumPy inference and minimized model card. It has no training corpus, Torch, SQLite persistence, screenshot runtime, Streamlit, Spark or Kafka worker. Exact deployment/custom hostnames are trusted; a private server key is required and never embedded in public assets. Keys are held in page memory, scans require consent, query/fragments are stripped and submitted sites are never fetched. A per-instance limiter is not a distributed internet-facing quota; configure account-level controls appropriate to your deployment.

The user explicitly chose deploy-ready ZIPs rather than login/live publication. Vercel remote build/deploy has **not** been executed. Local checks used Python 3.11; the export selects Vercel Python 3.12. Verify the actual preview after setting the sensitive key in your account. Do not claim a live URL, remote build pass, public-scale capacity, 100% accuracy or independent security certification.

## Delivery and setup

Complete ZIP: source, selected URL model plus all five candidates, improved CNN/sidecar and aggregate reports. Separate source ZIP excludes learned artifacts. Separate Vercel ZIP is the exact lean project root; see its README and `docs/vercel.md`. Run local `bash scripts/setup_mac.sh`, activate the environment, `make doctor`, then `make launch`. Load the extension manually with Chrome Developer mode. Cloud extension generation takes one exact HTTPS deployment origin and produces a separate narrow-permission build.

Inventory measured before final report regeneration: 167 maintained code/config/test/doc files, 10,509 text lines including 7,979 Python lines; excludes evidence/models/caches. The approximate 12,000 LOC target is not padded or claimed. Dependency download and several GB of disk are needed for a fresh full environment. Review dataset/model redistribution rights before public redistribution. Prior-release evidence is explicitly retained under historical report names.
