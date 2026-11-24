# 2.5.0

- Added explicit opt-in automatic domain checks for existing/new tabs, navigation and periodic active-tab rechecks.
- Added phishing-only friendly in-page warnings, real returned reasons, toolbar status, dismissal and optional browser notifications.
- Added debounce, bounded concurrency, duplicate-warning suppression, stale-response rejection and OFF/key-revocation cleanup.
- Kept trusted-only key storage and per-capture screenshot consent; automatic requests now send origin only.
- Added deterministic Node behavior tests, isolated Chromium navigation/warning tests, lockfile and CI steps.
- URL/CNN weights and their benchmark status are unchanged. No dashboard live-event bridge or redesigned three-page frontend is claimed.

# 2.4.0

- Added authorized Phish360 AES archive preparation, explicit publisher label mapping, domain/content isolation, and reproducible training/calibration scripts.
- Trained ImageNet-initialized ResNet18, restoring epoch six of eleven. First locked test: precision 92.85%, recall 80.66%.
- Added a documented calibration-only sensitivity policy revision after observing that first test; current benchmark audit: precision 88.16%, recall 88.36%, false-positive rate 10.69%. Independent confirmation remains outstanding.
- Preserved the original evaluation, existing models/releases and user Desktop/Downloads data. No raw screenshots or extraction password are bundled.

# 2.3.0

- Added bounded, offline ResNet18 transfer inference and exact train/runtime preprocessing checks.
- Added deterministic pixel deduplication and group-disjoint selection/calibration preparation.
- Added a reproducible transfer-training entry point with private epoch checkpoints and safe atomic tensor writes.
- Compared three pretrained CNN feature families and two fine-tuning recipes; calibration/test/source-held-out data remain separate.
- Included measured target failure and cross-source limitations; no 85% claim is made.

# 2.2.0

- Separate Vercel URL-only FastAPI/web export with exact host trust, private in-memory key, manual consent, query stripping and no persistence.
- Exporter allowlists modules/files and excludes datasets, training/CNN dependencies, runtime state and secrets.
- Narrow HTTPS Chrome extension builder for one chosen deployment origin.
- Identified zero legitimate training paths; origin-only retraining removes that shortcut and exposes conservative review notices without domain allowlists.
- Spatial CNN candidate with layout pooling/dropout improved validation and measured held-out results; checkpoint/threshold/promotion use validation only.
- Full regression, real desktop/mobile web flow, container and bundle evidence recorded in BUILD_REPORT.

# 2.1.0

- Real image corpus preparation with domain/content component isolation, ambiguous-label exclusions and aggregate evidence.
- CPU CNN training with class balance, validation-only threshold selection, early stopping and held-out measurements; weights included only in complete bundle.
- Model digest/sidecar validation, finite weight checks and safe bounded loading.
- Private resized training cache with source fingerprint checks.
- URL and vision launcher readiness probes, diagnostic-failure key cleanup and model-aware doctor.
- API vision capability discovery corrected and regression tested; actual toolbar-to-trained-backend URL/image flow exercised.
- Separate optional CPU vision Docker recipe and configurable Compose ports. Container execution status is stated in BUILD_REPORT.

# Changelog

## 2.0.0 — source release

- Replaced empty scaffold modules with integrated URL feature/training/API implementations.
- Added Spark ETL and checkpointed Kafka-to-Parquet scoring.
- Added acknowledged Python Kafka producer/consumer with minimized dead letters.
- Added explicit OFF-by-default, manual-only Chrome extension and session-scoped API key.
- Added optional standalone experimental screenshot CNN train/infer path.
- Added non-destructive merge preview, code backups, journal and symlink refusal.
- Added executable tests, deployment recipes, CI and operational documentation.

No pretrained real-world model or production detection accuracy is included. See BUILD_REPORT.


## 2.0.1 — final project hardening

- Validated the original URL before query minimization on every portable inference path.
- Rejected duplicate Content-Length and ambiguous transfer framing before body processing.
- Restricted source packaging to reviewed directories and excluded runtime session reports,
  key material, learned binaries and database side-files.
- Added a managed local API/dashboard launcher, readiness checks and ephemeral-key cleanup.
- Added complete runnable bundling with model/report identity checks and full checksums.
- Added a read-only environment doctor and a bounded loopback API benchmark.
- Preserved pre-existing virtual environments during setup and updated SPDX packaging metadata.
