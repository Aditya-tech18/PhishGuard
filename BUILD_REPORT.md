# 2.6.1 connection fix and main-folder transfer

Read README.md, docs/connection-fix-verification.json, COPY_REPORT.json and DATA_VERIFICATION.json for current outcomes.

# PhishGuard 2.6 verification

## Implemented in this release

- Three supplied-HTML-derived dashboard routes, self-hosted fonts/assets and compiled styles.
- Same-origin local session bootstrap, authenticated memory-only browser report channel and WebSocket snapshots.
- Stable unpacked extension identity, exact backend-origin external-message allowlist, dashboard pairing, acknowledged ON/OFF, pause/resume, tab focus/close and session feedback.
- Actual origin-only URL-model results in the dashboard; explicit-consent screenshot upload for the existing CNN.
- One-command local startup; code backup merge and isolated versioned model/report installation.

## Actual checks

- 72 Python API, browser-session, input guard, security, merge, URL-feature and serverless checks passed.
- 20 extension Node behavior tests passed.
- Real isolated Chromium 159 / Playwright 1.65.1 automatic-warning regression suite passed: suspicious-only warning DOM, inert reason text, dismissal, navigation, OFF cleanup and late-response rejection. Deterministic local fixture API; synthetic sites only.
- Real isolated Chromium dashboard integration passed: local bootstrap, extension pairing, dashboard ON, new-tab actual URL-model result via WebSocket, origin-only privacy, three routes, OFF tab removal and no page JavaScript errors. Optional host permissions were pregranted in a test-only extension copy; native permission dialogs were not automated.
- Merged Desktop project independently passed all three page checks and both actual model inference smoke checks using its versioned installed artifacts.
- Both actual models loaded. Authorized URL inference and a synthetic-image CNN inference smoke passed. This is not a new accuracy evaluation.
- ZIP CRC and per-member SHA-256 verification are performed by the release packager.

A broader model-training test collection initially could not run because scikit-learn was absent from the temporary test environment. The selected 72 checks above ran successfully. No claim is made that all project tests, cloud CI, Spark/Kafka services, OS notifications or Chrome Web Store publication were exercised in this release.

## Models unchanged

URL model `3a4516d9641014ee`: recorded held-out precision 91.24%, recall 82.20%. CNN ResNet18 `experimental-cnn-v1-5eb842485190`: previously observed audit precision 88.16%, recall 88.36%. The CNN threshold operating policy was revised after seeing an earlier test evaluation; a fresh independent evaluation remains required. This release changes UI/integration, not model weights.

## Visual scope

Approved HTML styling and structure are reused. Live controls, evidence, missing-capability labels and session rows replace mock content. Exact pixel equality has not been established. Reference illustrations are decorative, not evidence of a measured scan. Third-party reference imagery/font rights remain with their respective owners.

## Safety and delivery

Local only. No personal Chrome profile was used for automated tests and no live phishing website was visited. No raw data, private screenshots, secrets, virtual environments or event databases are included in the ZIP. Desktop merge preserves existing data/models/environments and backs up replaced code. Consult the merge journal for the actual target operations.
