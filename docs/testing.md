# Verification and reproducibility

## Fast checks

```bash
pip install -e '.[api,ml,streaming,dashboard,dev]'
make lint
make test
```

The fast suite excludes Spark, real-broker, image-model and browser markers. It checks contracts,
normalization, label polarity, leakage isolation, portable parity, malformed artifacts,
threshold/metric handling, HTTP limits/auth, retention, merge/rollback and packaging exclusions.
Failures must remain visible; no general retry or skip turns a failing assertion into success.

## Optional integration layers

| Layer | Setup | Command |
| --- | --- | --- |
| Spark URL and image ETL | Java 17, extras spark/images/ml | `pytest -m spark -v` |
| CNN and site-manifest isolation | Torch, Pillow, API test dependencies | `pytest -m vision -v` |
| Actual Kafka round-trip | Isolated broker and explicit opt-in | `PHISHGUARD_TEST_KAFKA=true pytest -m kafka -v` |
| Chromium extension toolbar | browser extra and installed Chromium | `PHISHGUARD_TEST_BROWSER=true pytest -m browser -v` |

For browser setup:

```bash
pip install -e '.[browser]'
python -m playwright install chromium
```

The browser test uses a fresh temporary profile. It triggers the actual extension toolbar
through Chromium's supported test protocol, attaches to the real popup, exercises its controls
and talks only to a deterministic local fixture server. Its synthetic `.test` page is fulfilled
locally; no victim website or personal browser profile is used. The API service itself is
verified separately through FastAPI tests and actual HTTP/container probes.

The test proves OFF/default behavior, explicit consent, query/fragment minimization,
session-key controls, optional screenshot gating and a deliberate visible-tab JPEG submission.
It does not establish Chrome Web Store review, every Chromium release or malware resistance.

## Crash/replay and checkpoint tests

`scripts/local_integration.py` starts its own Kafka 4.x instance in a new scratch directory.
It verifies acknowledged prediction output and stable identity, then injects a crash after
acknowledged output and before input commit. Restarting the same group must replay that input.
Multiple prediction rows with one event ID are the expected at-least-once outcome, not a bug
hidden behind an exactly-once claim. Downstream deduplication remains required.

The optional Spark stage reads valid and invalid events, writes minimized Parquet and restarts
from the same checkpoint. No extra rows may appear without new input. The helper shuts down
only its own broker and retains scratch logs. It never targets an existing production cluster.

## Full dataset checks

Fixtures catch regressions quickly, but they are not a full-data benchmark. This build also
ran the real URL table through curation/training/ETL and inspected the complete existing image
corpus in Spark. Initial memory and boolean-partition aggregation failures were fixed and the
entire image run repeated successfully. See BUILD_REPORT for counts and evidence.

Structural image success does not verify semantic labels. Duplicate groups are findings for
review, not automatic permission to discard source files. Raw datasets were read-only throughout.

## Distribution checks

The packager excludes data, model artifacts, secrets, environments and caches. It writes an
internal SHA-256 manifest, tests ZIP CRC and compares archived bytes against source. A fresh
extraction is tested with its own source import path, preventing an editable install from
accidentally testing the original working tree instead of the delivered archive.

The default Docker image was built and run as a non-root user with read-only root filesystem,
no capabilities and a read-only deployment model. HTTP authentication, host rejection and
actual selected-model inference were exercised. Optional vision-image builds and remote CI
execution are separate acceptance boundaries, not implied by those local checks.

## Honest reporting

Use the final build report's actual counts, dependency snapshot and scanner outcomes. Coverage
is statement coverage for the measured run, not a security score. Externally executed helpers
may cover paths absent from pytest coverage; do not add them into a fictitious percentage.
A clean dependency audit covers its queried package database, not every JVM jar/base image or
future advisory. Warnings and unexecuted checks remain visible in the report.
