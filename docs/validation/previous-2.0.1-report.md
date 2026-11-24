# PhishGuard 2.0.1 — release verification

This release provides the implemented A–J project, selected URL model, all five candidate
numeric artifacts and matching aggregate reports in one runnable ZIP. It includes no raw
dataset, private environment, runtime session key, database or presentation files.

## Release inventory

- Maintained source/config/test/documentation files: **148**.
- Maintained text lines: **9421**. Python source/scripts/tests: **6830 lines**.
- Counts exclude generated validation logs, learned artifacts and binary documentation images.
- The earlier approximate 12,000-line engineering target is not met. No padding or generated
  fixture rows are counted as code to manufacture that target.
- A separate source-only ZIP excludes learned artifacts and runtime reports for code review.
- The complete ZIP includes the selected model and matching reports so URL inference works
  after setup without rerunning training or copying the existing Desktop corpus.

## Executed release checks

| Check | Actual result |
| --- | --- |
| Complete pytest run, all optional markers enabled | **135 passed**, 9 warnings, 141.61 seconds |
| Included in that run | Unit/API, models, image/CNN, real Spark, isolated Kafka and Chromium toolbar/screenshot |
| Measured statement coverage | **75%** of phishguard Python package statements |
| Source/script/test Ruff | Passed |
| Python, extension JS and shell syntax | Checked before packaging |
| Source security scan | No medium/high findings; 2 reviewed low-severity subprocess findings |
| Fresh standard-profile dependency audit | No known vulnerabilities found |
| New environment install from complete ZIP | Passed using its own setup script and tested constraints |
| Fresh dependency consistency | No broken requirements |
| Fresh installed doctor | Ready, all required basic checks passed |
| Fresh API/dashboard launcher | Authenticated model smoke passed, services stopped and key removed |
| Docker API image | Built and exercised as UID 10001, read-only root, capabilities dropped |
| Container HTTP | Health 200, authenticated prediction 200, missing key 401, unexpected host 400 |
| Full URL Spark ETL | **58,471** curated unique rows |
| Full image Spark ETL | **21,311 images**, **4,659,375,662 bytes**, all structurally valid |
| Image duplicate groups | **609** content-hash groups surfaced for review |
| Kafka injected crash | Output-before-commit crash replayed one input, yielding 3 rows with 1 stable event ID |
| Spark checkpoint restart | 3 rows (2 valid + 1 minimized invalid), no extra rows after restart |
| Real dashboard browser rehearsal | URL/result, model, data-quality and overview views, no console errors |
| Local API benchmark | 500/500 HTTP 200, concurrency 8, p95 about 14.0 ms, about 716 requests/sec |
| ZIP packaging | Exclusions, identity checks, CRC, archived byte comparison and SHA-256 manifests |

The benchmark is a short loopback experiment on macOS ARM64 / Python 3.11.18 with an explicit
high quota and storage off. It does not establish public capacity, a latency SLO or thousands
of concurrent users. Coverage is a measurement, not a security certification. Pytest warnings
include upstream Starlette/httpx and Spark/distutils deprecations.

## Implemented components

A. Validated configuration, shared Pydantic schemas, bounded atomic JSON/artifact operations.
B. Explicit-polarity CSV ingestion, read-only inspection/inventory and query-aware curation.
C. Spark URL normalization/features/Parquet plus four-image Arrow batches for image metadata.
D. Shared 24-feature lexical schema and bundled-PSL registrable-domain grouping.
E. Logistic, decision tree, random forest, gradient boosting and Gaussian naive Bayes, with
   validation-only selection, portable numeric JSON, calibration, domain bootstrap intervals,
   independent-file evaluation, descriptive drift and quality-gated local model registry.
F. Acknowledged Kafka publication, offset-after-output consumer, minimized DLQ and Spark sink.
G. API-key authentication, trusted hosts, body deadline/length/chunk/byte limits, local quota,
   minimized errors, numeric metrics, private bounded HMAC metadata and cleanup.
H. Streamlit URL/image controls, model/calibration report, data quality, runtime overview and
   metadata deletion. Raw dataset browsing and telemetry are absent.
I. MV3 extension OFF by default, session key and per-URL consent. Screenshot capture has a
   separate opt-in, fresh consent, activeTab scope and server-capability check before capture.
J. Safe merge preview/backups/journal, rollback refusing later edits, environment preservation,
   doctor, managed local launcher, source/complete packagers, CI and deployment documentation.

## Security issues addressed during the final audit

- Original URL validation now happens before query removal, including controls and length.
- IDNA expansion cannot produce an accepted normalized URL above the supported length.
- Duplicate Content-Length, signed/whitespace lengths and ambiguous transfer framing fail closed.
- Numeric model loads reject symlink paths, oversized inputs and non-finite JSON values.
- Source packaging uses a reviewed top-level allowlist and excludes all runtime reports,
  session keys, private-key files, learned binaries, database side-files and virtual environments.
- Setup preserves unmarked pre-existing environments instead of silently modifying them.
- Managed local launch verifies model/report identity, checks readiness and generates a private
  temporary key. Normal stop/startup-error handling stops only owned child process groups.
- SPDX packaging metadata and the Docker license copy are corrected for this patch release.

## Dataset-specific evaluation

Source table: 60,000 rows, semicolon-delimited, explicit legitimate=0 and phishing=1 mapping.
59,959 URL rows passed normalization and 41 failed. Query stripping produced 58,475 unique
normalized URLs. Four contradictory normalized URLs were excluded entirely in a separate
private working copy, leaving **58,471** rows. Source data was not edited.

Validation PR-AUC subject to the configured false-positive constraint selected random forest.
Training rows fit the scaler and estimator. Test labels did not choose algorithm/threshold.
All five candidates passed sklearn/portable parity checks before selection.

- Model version: `dd73426d432f5b77`, query policy strip, threshold about 0.43.
- Domain-isolated train/validation/test rows: **33,088 / 8,884 / 16,499**.
- Held-out precision **98.9788%**, recall **97.0967%**, F1 **98.0287%**.
- PR-AUC **0.997990**, ROC-AUC **0.995653**, false-positive rate **1.88877%**.
- Confusion counts: TN 5610, FP 108, FN 313, TP 10468.
- Calibration, subgroup metrics and 100 domain-bootstrap repetitions are in reports/evaluation.json.

These are results on this dataset/split. Dataset provenance, remaining labels and independent
source/time generalization have not been established. They do not mean 98% internet-wide
accuracy or guarantee that a low-risk URL is safe. The source code license does not establish
third-party dataset/model redistribution rights. Learned artifacts are supplied for local use.

## Explicit remaining acceptance boundaries

- No independent penetration test, long-duration soak, multi-tenant identity system or
  distributed rate limit is claimed. The default remains a local authenticated deployment.
- Remote GitHub Actions, public GitHub push, cloud/TLS hosting, registry publication and
  Chrome Web Store approval were not executed. Supplied workflow files are not marked run.
- The default URL API image was built/run. Optional vision-image builds and Compose multi-service
  launch were not separately executed.
- CNN mechanics, site-manifest leakage checks, opt-in API and actual visible-tab capture were
  tested. Independently evaluated real-world screenshot weights and validated score fusion
  are not included. Optional image inference remains OFF until explicitly configured.
- Python auditing does not comprehensively cover JVM jars, container OS packages or future advisories.

## Installation and preservation

Extract the complete ZIP into a new directory. Run setup_mac.sh, activate the new environment,
then make doctor and make launch. docs/running.md covers direct configuration and optional runtimes.
Do not unzip over the existing Desktop data tree. install_to_mac.sh previews code merges first,
backs up replacements and protects data, models, reports, .env, Git and environments.

Existing Desktop code/data was never overwritten by this build. Temporary Kafka/browser/API
sessions and Docker test VM were stopped. Personal Chrome profiles and the default Docker
context were not used. Evidence is in docs/validation, with workspace paths redacted.
