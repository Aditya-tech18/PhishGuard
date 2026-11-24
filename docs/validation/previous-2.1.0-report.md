# PhishGuard 2.1.0 — actual release verification

Complete local source repository, trained URL artifacts, real-data experimental CNN, aggregate reports and safe installation/merge tooling. No presentation is included. The existing Desktop/PhishGuard folder and its raw data were read only and remain untouched.

## Scope and inventory

150 maintained code/config/test/documentation files; 9,664 text lines, including 7,253 Python lines. Evidence, weights and caches are excluded from this count. The approximate 12,000-line target is not met; no filler is counted. A source-only ZIP excludes learned models. The complete ZIP includes models and reports and runs without copying the raw corpus.

## Upgraded implementation

- Spark ETL, Kafka ingestion/prediction and checkpoint restart tooling; URL model training/evaluation and portable numeric inference.
- FastAPI local authenticated backend and Streamlit dashboard, with a managed launcher and readiness checks.
- MV3 Chrome extension, OFF by default, manual URL consent; separate image opt-in plus consent for each visible-tab capture. Query/fragment stripping, session-only key and no retained images.
- Real image corpus preparation, filename-derived domain/content component grouping, contradictory-label exclusions, class-balanced CNN training and optional bounded resized cache.
- Vision weights loaded with bounded reads and Torch weights-only loading, finite tensor checks, SHA-256 identity/sidecar validation and validation-selected threshold.
- Launcher loads the included URL/CNN models, tests both authenticated routes, stops only owned processes and removes its transient session key even if diagnostic writes fail.
- Setup, model-aware doctor, safe merge preview/rollback, CI workflows, deployment examples, tests, docs, source and complete packagers with CRC/hash verification.

## Model measurements

URL model: selected RandomForest, version dd73426d432f5b77. 58,471 curated unique URLs with registrable-domain split; train 33,088, validation 8,884, test 16,499. Test precision 98.98%, recall 97.10%, F1 98.03%, FPR 1.89%. Model selection uses validation only. These scores describe this dataset, not future browsing safety.

Screenshot model: experimental-cnn-v1-15ce04585ab5. Preparation inspected 21,311 images, rejected 13 filename/file records, removed 579 images across 18 conflicting-label content groups and 6,813 duplicates, yielding 13,906 unique images. Split: train 8,780, validation 2,585, test 2,541. No observed domain-component or content overlap. Filename-derived host provenance and publisher labels were not independently verified; no temporal/source holdout exists.

Five training epochs ran with early stopping; epoch 2 restored. Threshold 0.64 selected on validation only with 5% empirical FPR constraint. Held-out test: precision 47.10%, recall 29.80%, F1 36.50%, ROC AUC 0.8237, FPR 3.57% (TN2214, FP82, FN172, TP73). This CNN misses many phishing screenshots. It is experimental assistance, not the main detector or a calibrated safety probability. Test results were not used to tune the release.

## Executed checks for 2.1.0

**139 tests passed**, 9 warnings, 59.17 seconds, **76% statement coverage**; all Spark, Kafka, vision and browser markers enabled. See docs/validation/upgrade-checks.json and aggregate model/preparation reports.

ZIP extraction and an independent installed application passed doctor and API/dashboard URL/CNN launch probes. That install reused the tested dependencies; a fresh network dependency resolution was not repeated for 2.1.0.

- Managed API/dashboard startup: passed with actual included URL model and real trained CNN; authenticated URL and image predictions passed; stop/key cleanup passed.
- Actual isolated Chromium toolbar against real backend: URL prediction, explicit screenshot capture/inference, ON/OFF, fresh consent and key-clear passed. This exposed and fixed missing vision capability fields in health; a regression assertion now covers them.
- Compose API/vision/streaming configuration validation: passed. Dependency consistency: passed. Ruff and JavaScript syntax: passed. Medium/high source security scan: no findings.
- Packager validates model/report identities, excludes private/raw/runtime files, checks ZIP CRC, compares archived bytes and writes SHA-256 manifests/checksums.

## Historical integration evidence and boundaries

The previous 2.0.1 full-data Spark ETL checked 21,311 images (4,659,375,662 bytes). Kafka output-before-commit crash replay produced three rows with one stable event ID; checkpoint restart added no extra rows. The previous API-only Docker image ran non-root with a read-only filesystem and passed health/auth/host probes. Prior evidence is retained explicitly as historical, not relabeled as current container testing.

The new optional CPU vision Docker recipe has configuration validation but has NOT been built/run here. Host API/CNN inference is tested. Available disk space was insufficient to safely add a full new VM/container dependency stack without deleting unrelated user data. The host launcher is the verified run path. No cloud deployment, Chrome Web Store publication, independent penetration test or externally certified security has been performed. Load unpacked is a manual Chrome installation step; moving a folder does not install an extension. Spark needs Java 17; Kafka needs a broker. Setup requires network access for dependencies.

No software or learned detector can truthfully be promised 100% perfect. This release records actual outcomes and includes an executable local project, not an assertion of guaranteed phishing detection. Review dataset/model redistribution rights before public release.
